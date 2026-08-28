import json
from dataclasses import dataclass, field

from app.llm.client import LLMClient
from app.workflows.contracts import BugWorkflowInput, MeetingWorkflowInput
from app.workflows.utils import load_json_object, optional_text


WORKFLOW_INTENT_CLASSIFICATION_PROMPT = """You are a workflow intent classifier for Ella Agent.
Return JSON only.

Decide whether the user request should run a deterministic workflow or stay in normal chat.

Supported workflows:
- meeting: for requests to summarize meeting notes, extract action items, create a memo, or send/share a meeting summary.
- bug: for requests to analyze a bug report, produce root cause analysis, draft a Jira comment, or post a Jira update.

Output schema:
- route: string, one of "workflow" or "chat"
- workflow_type: string, one of "meeting", "bug", or ""
- rationale: short string

Rules:
- If the message does not clearly ask for one of the supported workflows, return route="chat".
- If the message clearly asks for one of the supported workflows, return route="workflow" with the best matching workflow_type.
- Bug workflow is only for explicit bug-analysis/update tasks such as analyzing a bug report, generating root cause analysis, drafting a Jira comment, or posting a Jira update.
- Requests to merely search, list, fetch, look up, or query Jira bugs/issues/PRs should stay in normal chat so the agent can use tools instead of the bug workflow.
"""

WORKFLOW_SLOT_FILLING_PROMPT = """You are extracting workflow input fields for Ella Agent.
Return JSON only.

You will receive:
- workflow_type
- user request
- known_input

Output schema:
- route: string, one of "workflow" or "clarify"
- input: object
- missing_fields: string[]
- rationale: short string

Rules:
- Extract only fields relevant to the provided workflow_type.
- Use known_input as already confirmed fields and avoid contradicting it unless the user clearly corrects a value.
- If all required fields are available, return route="workflow".
- If required fields are still missing or unclear, return route="clarify".
- For meeting workflow input, use fields: transcript, meeting_title, channel, send_to_teams.
- For bug workflow input, use fields: bug_report, issue_key, post_to_jira.
- Default channel to "engineering" when omitted.
- Default send_to_teams and post_to_jira to false unless explicitly requested.
"""

WORKFLOW_CLARIFICATION_RESOLUTION_PROMPT = """You are resolving missing workflow inputs for Ella Agent.
Return JSON only.

You will receive:
- workflow_type
- original user request
- missing_fields
- user follow-up answer
- known_input

Output schema:
- route: string, one of "workflow" or "clarify"
- input: object
- missing_fields: string[]
- rationale: short string

Rules:
- Preserve the existing workflow_type; do not classify a new workflow.
- Use known_input as already confirmed fields and add newly resolved fields from the follow-up answer.
- If the follow-up answer fills all required missing fields, return route="workflow".
- If fields are still missing or unclear, return route="clarify".
- You may return only the newly resolved fields inside input. The system will merge them with previously known input.
- For meeting workflow input, use fields: transcript, meeting_title, channel, send_to_teams.
- For bug workflow input, use fields: bug_report, issue_key, post_to_jira.
- Default channel to "engineering" when omitted.
- Default send_to_teams and post_to_jira to false unless explicitly requested.
"""


@dataclass(frozen=True)
class WorkflowPlan:
	workflow_type: str
	input_payload: dict[str, object]
	rationale: str = ""


@dataclass(frozen=True)
class WorkflowClarification:
	workflow_type: str
	missing_fields: list[str]
	message: str
	input_payload: dict[str, object] = field(default_factory=dict)
	rationale: str = ""


@dataclass(frozen=True)
class WorkflowIntent:
	route: str
	workflow_type: str = ""
	rationale: str = ""


class WorkflowPlanner:
	def __init__(self, llm_client: LLMClient | None = None) -> None:
		self._llm_client = llm_client or LLMClient()
		self._allowed_input_fields: dict[str, frozenset[str]] = {
			"meeting": frozenset(MeetingWorkflowInput.model_fields.keys()),
			"bug": frozenset(BugWorkflowInput.model_fields.keys()),
		}
		self._required_input_fields: dict[str, tuple[str, ...]] = {
			"meeting": tuple(
				name for name, field in MeetingWorkflowInput.model_fields.items() if field.is_required()
			),
			"bug": tuple(
				name for name, field in BugWorkflowInput.model_fields.items() if field.is_required()
			),
		}
		self._clarification_field_prompts: dict[str, dict[str, str]] = {
			"meeting": {
				"transcript": "会议 transcript 或会议纪要原文",
				"meeting_title": "会议标题",
				"channel": "要发送到的 Teams channel",
			},
			"bug": {
				"bug_report": "bug report 的具体描述",
				"issue_key": "Jira issue key，例如 BUG-123",
			},
		}

	def _sanitize_input_payload(self, workflow_type: str | None, payload: dict[str, object]) -> dict[str, object]:
		if workflow_type is None:
			return {}
		allowed_fields = self._allowed_input_fields.get(workflow_type)
		if allowed_fields is None:
			return {}
		return {
			key: value
			for key, value in payload.items()
			if isinstance(key, str) and key in allowed_fields
		}

	def _sanitize_missing_fields(self, workflow_type: str | None, missing_fields: list[object]) -> list[str]:
		allowed_fields = self._allowed_input_fields.get(workflow_type or "")
		return [
			item.strip()
			for item in missing_fields
			if isinstance(item, str) and item.strip() and (allowed_fields is None or item.strip() in allowed_fields)
		]

	@staticmethod
	def _deduplicate_fields(fields: list[str]) -> list[str]:
		seen: set[str] = set()
		result: list[str] = []
		for field_name in fields:
			if field_name in seen:
				continue
			seen.add(field_name)
			result.append(field_name)
		return result

	def _detect_missing_required_fields(self, workflow_type: str | None, payload: dict[str, object]) -> list[str]:
		if workflow_type is None:
			return []
		required_fields = self._required_input_fields.get(workflow_type)
		if required_fields is None:
			return []
		missing_fields: list[str] = []
		for field_name in required_fields:
			value = payload.get(field_name)
			if value is None:
				missing_fields.append(field_name)
				continue
			if isinstance(value, str) and not value.strip():
				missing_fields.append(field_name)
		return missing_fields

	def _build_clarification_message(self, workflow_type: str, missing_fields: list[str]) -> str:
		field_prompts = self._clarification_field_prompts.get(workflow_type, {})
		prompt_parts = [field_prompts.get(field_name, field_name) for field_name in missing_fields]
		if not prompt_parts:
			return f"要继续执行 {workflow_type} workflow，我还需要补充一些信息。"
		if len(prompt_parts) == 1:
			return f"要继续执行 {workflow_type} workflow，我还需要{prompt_parts[0]}。"
		joined_parts = "、".join(prompt_parts)
		return f"要继续执行 {workflow_type} workflow，我还需要这些信息：{joined_parts}。"

	def _parse_intent_payload(self, payload: dict[str, object]) -> WorkflowIntent | None:
		route = optional_text(payload.get("route"))
		if route == "chat":
			return None
		if route != "workflow":
			return None
		workflow_type = optional_text(payload.get("workflow_type"))
		if not workflow_type or workflow_type not in self._allowed_input_fields:
			return None
		return WorkflowIntent(
			route=route,
			workflow_type=workflow_type,
			rationale=optional_text(payload.get("rationale")),
		)

	def _parse_slot_filling_payload(
		self,
		payload: dict[str, object],
		*,
		workflow_type: str,
		known_input: dict[str, object] | None = None,
		default_rationale: str = "",
	) -> WorkflowPlan | WorkflowClarification | None:
		route = optional_text(payload.get("route"))
		if route == "chat":
			return None
		input_payload = payload.get("input")
		if input_payload is None:
			input_payload = {}
		if not isinstance(input_payload, dict):
			raise ValueError("WorkflowPlanner input must be a JSON object.")
		input_payload = self._sanitize_input_payload(workflow_type, input_payload)
		effective_payload = {
			**self._sanitize_input_payload(workflow_type, known_input or {}),
			**input_payload,
		}
		inferred_missing_fields = self._detect_missing_required_fields(workflow_type, effective_payload)
		rationale = optional_text(payload.get("rationale")) or default_rationale
		if route == "clarify":
			missing_fields = payload.get("missing_fields")
			if not isinstance(missing_fields, list):
				raise ValueError("WorkflowPlanner missing_fields must be a JSON array.")
			merged_missing_fields = self._deduplicate_fields(
				self._sanitize_missing_fields(workflow_type, missing_fields) + inferred_missing_fields
			)
			if not merged_missing_fields:
				return None
			return WorkflowClarification(
				workflow_type=workflow_type,
				missing_fields=merged_missing_fields,
				message=self._build_clarification_message(workflow_type, merged_missing_fields),
				input_payload=input_payload,
				rationale=rationale,
			)
		if route != "workflow":
			return None
		if inferred_missing_fields:
			return WorkflowClarification(
				workflow_type=workflow_type,
				missing_fields=inferred_missing_fields,
				message=self._build_clarification_message(workflow_type, inferred_missing_fields),
				input_payload=input_payload,
				rationale=rationale,
			)

		return WorkflowPlan(
			workflow_type=workflow_type,
			input_payload=input_payload,
			rationale=rationale,
		)

	def _parse_plan_payload(self, payload: dict[str, object]) -> WorkflowPlan | WorkflowClarification | None:
		workflow_type = optional_text(payload.get("workflow_type"))
		if not workflow_type:
			return None
		return self._parse_slot_filling_payload(payload, workflow_type=workflow_type)

	async def classify_intent(self, message: str) -> WorkflowIntent | None:
		text = await self._llm_client.invoke_text(
			[
				{"role": "system", "content": WORKFLOW_INTENT_CLASSIFICATION_PROMPT},
				{"role": "user", "content": message.strip()},
			]
		)
		payload = load_json_object(text, "WorkflowIntentClassifier")
		return self._parse_intent_payload(payload)

	async def fill_workflow_slots(
		self,
		*,
		workflow_type: str,
		message: str,
		known_input: dict[str, object] | None = None,
		default_rationale: str = "",
	) -> WorkflowPlan | WorkflowClarification | None:
		text = await self._llm_client.invoke_text(
			[
				{"role": "system", "content": WORKFLOW_SLOT_FILLING_PROMPT},
				{
					"role": "user",
					"content": json.dumps(
						{
							"workflow_type": workflow_type,
							"user_request": message.strip(),
							"known_input": known_input or {},
						},
						ensure_ascii=False,
						indent=2,
					),
				},
			]
		)
		payload = load_json_object(text, "WorkflowSlotFiller")
		return self._parse_slot_filling_payload(
			payload,
			workflow_type=workflow_type,
			known_input=known_input,
			default_rationale=default_rationale,
		)

	async def plan(self, message: str) -> WorkflowPlan | WorkflowClarification | None:
		intent = await self.classify_intent(message)
		if intent is None:
			return None
		return await self.fill_workflow_slots(
			workflow_type=intent.workflow_type,
			message=message,
			default_rationale=intent.rationale,
		)

	async def resolve_clarification(
		self,
		*,
		clarification: WorkflowClarification,
		original_message: str,
		followup_message: str,
	) -> WorkflowPlan | WorkflowClarification | None:
		text = await self._llm_client.invoke_text(
			[
				{"role": "system", "content": WORKFLOW_CLARIFICATION_RESOLUTION_PROMPT},
				{
					"role": "user",
					"content": json.dumps(
						{
							"workflow_type": clarification.workflow_type,
							"original_message": original_message.strip(),
							"known_input": clarification.input_payload,
							"missing_fields": clarification.missing_fields,
							"followup_message": followup_message.strip(),
						},
						ensure_ascii=False,
						indent=2,
					),
				},
			]
		)
		payload = load_json_object(text, "WorkflowClarificationResolver")
		return self._parse_slot_filling_payload(
			payload,
			workflow_type=clarification.workflow_type,
			known_input=clarification.input_payload,
			default_rationale=clarification.rationale,
		)

	@staticmethod
	def serialize_plan(plan: WorkflowPlan | WorkflowClarification | None) -> str:
		if plan is None:
			return json.dumps({"route": "chat"}, ensure_ascii=False)
		if isinstance(plan, WorkflowClarification):
			return json.dumps(
				{
					"route": "clarify",
					"workflow_type": plan.workflow_type,
					"input": plan.input_payload,
					"missing_fields": plan.missing_fields,
					"clarification_message": plan.message,
					"rationale": plan.rationale,
				},
				ensure_ascii=False,
			)
		return json.dumps(
			{
				"route": "workflow",
				"workflow_type": plan.workflow_type,
				"input": plan.input_payload,
				"rationale": plan.rationale,
			},
			ensure_ascii=False,
		)