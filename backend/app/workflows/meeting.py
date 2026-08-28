import json
from typing import TYPE_CHECKING
from uuid import uuid4

from app.llm.client import LLMClient
from app.services.tool_dispatcher import ToolDispatcher
from app.workflows.base import WorkflowContext, WorkflowRunner, WorkflowRunResult, WorkflowStepOutcome, WorkflowStepStatus
from app.workflows.utils import load_json_object, optional_text, string_list

if TYPE_CHECKING:
	from app.memory.memory_manager import MemoryManager


SUMMARY_PROMPT = """You are the SummaryStep in a deterministic workflow.
Return JSON only.
Generate an object with these fields:
- title: string
- summary: string
- key_points: string[]
- decisions: string[]
- risks: string[]
- open_questions: string[]

Be concise, factual, and grounded in the transcript.
If information is missing, use empty strings or empty arrays.
"""

ACTION_ITEMS_PROMPT = """You are the ActionItemStep in a deterministic workflow.
Return JSON only.
Generate an object with one field:
- action_items: array of objects with fields title, owner, due_date, status, notes

Rules:
- Prefer explicit actions from the transcript.
- If owner or due_date is unknown, return an empty string.
- Use short normalized text.
"""

MEMO_PROMPT = """You are the MemoStep in a deterministic workflow.
Write a polished meeting memo in markdown.

Include these sections when information exists:
- Title
- Summary
- Key Decisions
- Action Items
- Risks / Open Questions

Keep the memo concise and ready to share in Teams.
Do not wrap the answer in code fences.
"""
class SummaryStep:
	name = "summary"

	def __init__(self, llm_client: LLMClient) -> None:
		self._llm_client = llm_client

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		messages = [
			{"role": "system", "content": SUMMARY_PROMPT},
			{
				"role": "user",
				"content": json.dumps(
					{
						"meeting_title": context.input_payload.get("meeting_title", ""),
						"transcript": context.input_payload["transcript"],
					},
					ensure_ascii=False,
					indent=2,
				),
			},
		]
		text = await self._llm_client.invoke_text(messages)
		payload = load_json_object(text, "SummaryStep")
		summary = {
			"title": optional_text(payload.get("title")) or optional_text(context.input_payload.get("meeting_title")),
			"summary": optional_text(payload.get("summary")),
			"key_points": string_list(payload.get("key_points")),
			"decisions": string_list(payload.get("decisions")),
			"risks": string_list(payload.get("risks")),
			"open_questions": string_list(payload.get("open_questions")),
		}
		if not summary["summary"]:
			raise ValueError("SummaryStep produced an empty summary.")
		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="summary",
			artifact=summary,
		)


class ActionItemStep:
	name = "action_items"

	def __init__(self, llm_client: LLMClient) -> None:
		self._llm_client = llm_client

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		messages = [
			{"role": "system", "content": ACTION_ITEMS_PROMPT},
			{
				"role": "user",
				"content": json.dumps(
					{
						"transcript": context.input_payload["transcript"],
						"summary": context.artifacts["summary"],
					},
					ensure_ascii=False,
					indent=2,
				),
			},
		]
		text = await self._llm_client.invoke_text(messages)
		payload = load_json_object(text, "ActionItemStep")
		raw_items = payload.get("action_items")
		if not isinstance(raw_items, list):
			raise ValueError("ActionItemStep output must include an action_items array.")

		action_items: list[dict[str, str]] = []
		for item in raw_items:
			if not isinstance(item, dict):
				continue
			title = optional_text(item.get("title"))
			if not title:
				continue
			action_items.append(
				{
					"title": title,
					"owner": optional_text(item.get("owner")),
					"due_date": optional_text(item.get("due_date")),
					"status": optional_text(item.get("status")) or "open",
					"notes": optional_text(item.get("notes")),
				}
			)

		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="action_items",
			artifact=action_items,
		)


class MemoStep:
	name = "memo"

	def __init__(self, llm_client: LLMClient) -> None:
		self._llm_client = llm_client

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		messages = [
			{"role": "system", "content": MEMO_PROMPT},
			{
				"role": "user",
				"content": json.dumps(
					{
						"meeting_title": context.input_payload.get("meeting_title", ""),
						"summary": context.artifacts["summary"],
						"action_items": context.artifacts["action_items"],
					},
					ensure_ascii=False,
					indent=2,
				),
			},
		]
		memo = (await self._llm_client.invoke_text(messages)).strip()
		if not memo:
			raise ValueError("MemoStep produced an empty memo.")
		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="memo",
			artifact=memo,
		)


class SaveMemoryStep:
	name = "save_memory"

	def __init__(self, memory_manager: "MemoryManager") -> None:
		self._memory_manager = memory_manager

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		memo = context.artifacts.get("memo")
		if not isinstance(memo, str) or not memo.strip():
			raise ValueError("SaveMemoryStep requires a memo artifact.")

		title = optional_text(context.input_payload.get("meeting_title"))
		if not title:
			summary = context.artifacts.get("summary", {})
			if isinstance(summary, dict):
				title = optional_text(summary.get("title"))

		keywords = [keyword for keyword in [title, optional_text(context.input_payload.get("channel"))] if keyword]
		content = memo if not title else f"{title}\n\n{memo}"
		serialized_keywords = ",".join(keywords) if keywords else None
		self._memory_manager.remember(context.session_id, "meeting_memo", content, serialized_keywords)
		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="memory_record",
			artifact={
				"saved": True,
				"memory_type": "meeting_memo",
				"keywords": keywords,
			},
		)


class SendTeamsStep:
	name = "send_teams"

	def __init__(self, tool_dispatcher: ToolDispatcher) -> None:
		self._tool_dispatcher = tool_dispatcher

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		if not context.input_payload.get("send_to_teams", False):
			return WorkflowStepOutcome(
				status=WorkflowStepStatus.SKIPPED,
				artifact_key="teams_delivery",
				artifact={
					"sent": False,
					"reason": "send_to_teams_disabled",
				},
			)

		memo = context.artifacts.get("memo")
		if not isinstance(memo, str) or not memo.strip():
			raise ValueError("SendTeamsStep requires a memo artifact.")

		channel = optional_text(context.input_payload.get("channel")) or "engineering"
		result = await self._tool_dispatcher.dispatch(
			"send_teams_message",
			{
				"channel": channel,
				"message": memo,
			},
		)
		if result.get("status") == "error":
			return WorkflowStepOutcome(
				status=WorkflowStepStatus.FAILED,
				artifact_key="teams_delivery",
				artifact=result,
				error=str(result.get("error") or "Teams delivery failed."),
			)

		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="teams_delivery",
			artifact={
				"sent": True,
				"channel": channel,
				"tool_result": result,
			},
		)


class MeetingWorkflow:
	workflow_type = "meeting"

	def __init__(
		self,
		llm_client: LLMClient,
		memory_manager: "MemoryManager",
		tool_dispatcher: ToolDispatcher,
		runner: WorkflowRunner | None = None,
	) -> None:
		self._runner = runner or WorkflowRunner()
		self._steps = [
			SummaryStep(llm_client),
			ActionItemStep(llm_client),
			MemoStep(llm_client),
			SaveMemoryStep(memory_manager),
			SendTeamsStep(tool_dispatcher),
		]

	async def run(
		self,
		*,
		session_id: str,
		transcript: str,
		meeting_title: str | None = None,
		channel: str = "engineering",
		send_to_teams: bool = False,
	) -> WorkflowRunResult:
		workflow_id = f"workflow-{uuid4().hex}"
		context = WorkflowContext(
			workflow_id=workflow_id,
			workflow_type=self.workflow_type,
			session_id=session_id,
			input_payload={
				"transcript": transcript,
				"meeting_title": meeting_title or "",
				"channel": channel,
				"send_to_teams": send_to_teams,
			},
			artifacts={"transcript": transcript},
		)
		return await self._runner.run(self.workflow_type, context, self._steps)