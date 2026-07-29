import json
from dataclasses import dataclass, field

from app.llm.client import LLMClient
from app.workflows.contracts import BugWorkflowInput, MeetingWorkflowInput
from app.workflows.utils import load_json_object, optional_text


WORKFLOW_PLANNER_PROMPT = """You are a workflow intent router for Ella Agent.
Return JSON only.

Decide whether the user request should run a deterministic workflow or stay in normal chat.

Supported workflows:
- meeting: for requests to summarize meeting notes, extract action items, create a memo, or send/share a meeting summary.
- bug: for requests to analyze a bug report, produce root cause analysis, draft a Jira comment, or post a Jira update.

Output schema:
- route: string, one of "workflow", "clarify", or "chat"
- workflow_type: string, one of "meeting", "bug", or ""
- input: object
- missing_fields: string[]
- clarification_message: string
- rationale: short string

Rules:
- If the message does not clearly ask for one of the supported workflows, return route="chat".
- Do not invent missing required workflow inputs. If a required field is missing, return route="clarify" and ask one concise follow-up question.
- When route="clarify", include already-known workflow input fields inside input.
- For meeting workflow input, use fields: transcript, meeting_title, channel, send_to_teams.
- For bug workflow input, use fields: bug_report, issue_key, post_to_jira.
- Default channel to "engineering" when the user wants a meeting workflow and does not specify one.
- Default send_to_teams and post_to_jira to false unless the user explicitly asks to send/post.
"""

WORKFLOW_CLARIFICATION_RESOLUTION_PROMPT = """You are resolving missing workflow inputs for Ella Agent.
Return JSON only.

You will receive:
- workflow_type
- original user request
- missing_fields
- user follow-up answer

Output schema:
- route: string, one of "workflow" or "clarify"
- workflow_type: string
- input: object
- missing_fields: string[]
- clarification_message: string
- rationale: short string

Rules:
- If the follow-up answer fills all required missing fields, return route="workflow".
- If fields are still missing or unclear, return route="clarify" with one concise follow-up question.
- You may return only the newly resolved fields inside input. The system will merge them with previously known input.
- Preserve previously known workflow intent.
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


class WorkflowPlanner:
	def __init__(self, llm_client: LLMClient | None = None) -> None:
		self._llm_client = llm_client or LLMClient()
		self._allowed_input_fields: dict[str, frozenset[str]] = {
			"meeting": frozenset(MeetingWorkflowInput.model_fields.keys()),
			"bug": frozenset(BugWorkflowInput.model_fields.keys()),
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

	def _parse_plan_payload(self, payload: dict[str, object]) -> WorkflowPlan | WorkflowClarification | None:
		route = optional_text(payload.get("route"))
		if route == "chat":
			return None
		workflow_type = optional_text(payload.get("workflow_type"))
		input_payload = payload.get("input")
		if input_payload is None:
			input_payload = {}
		if not isinstance(input_payload, dict):
			raise ValueError("WorkflowPlanner input must be a JSON object.")
		input_payload = self._sanitize_input_payload(workflow_type, input_payload)
		if route == "clarify":
			missing_fields = payload.get("missing_fields")
			clarification_message = optional_text(payload.get("clarification_message"))
			if not workflow_type or not clarification_message:
				return None
			if not isinstance(missing_fields, list):
				raise ValueError("WorkflowPlanner missing_fields must be a JSON array.")
			return WorkflowClarification(
				workflow_type=workflow_type,
				missing_fields=self._sanitize_missing_fields(workflow_type, missing_fields),
				message=clarification_message,
				input_payload=input_payload,
				rationale=optional_text(payload.get("rationale")),
			)
		if route != "workflow":
			return None
		if not workflow_type:
			return None

		return WorkflowPlan(
			workflow_type=workflow_type,
			input_payload=input_payload,
			rationale=optional_text(payload.get("rationale")),
		)

	async def plan(self, message: str) -> WorkflowPlan | WorkflowClarification | None:
		text = await self._llm_client.invoke_text(
			[
				{"role": "system", "content": WORKFLOW_PLANNER_PROMPT},
				{"role": "user", "content": message.strip()},
			]
		)
		payload = load_json_object(text, "WorkflowPlanner")
		return self._parse_plan_payload(payload)

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
		return self._parse_plan_payload(payload)

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