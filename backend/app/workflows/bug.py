import json
from uuid import uuid4

from app.llm.client import LLMClient
from app.services.tool_dispatcher import ToolDispatcher
from app.workflows.base import WorkflowContext, WorkflowRunner, WorkflowRunResult, WorkflowStepOutcome, WorkflowStepStatus
from app.workflows.utils import load_json_object, optional_text, string_list


ANALYSIS_PROMPT = """You are the AnalysisStep in a deterministic bug workflow.
Return JSON only.
Generate an object with these fields:
- summary: string
- symptoms: string[]
- impacted_components: string[]
- suspected_factors: string[]
- evidence: string[]

Ground the analysis in the bug report only.
If information is missing, use empty strings or empty arrays.
"""

ROOT_CAUSE_PROMPT = """You are the RootCauseStep in a deterministic bug workflow.
Return JSON only.
Generate an object with these fields:
- root_cause: string
- confidence: string
- reasoning: string[]
- mitigations: string[]

Be explicit about uncertainty. Do not invent implementation details beyond the report and analysis.
"""

JIRA_COMMENT_PROMPT = """You are the JiraCommentStep in a deterministic bug workflow.
Write a concise Jira comment in markdown.

Include these sections when information exists:
- Summary
- Suspected Root Cause
- Evidence
- Proposed Mitigation / Next Steps

Do not wrap the answer in code fences.
"""
class AnalysisStep:
	name = "analysis"

	def __init__(self, llm_client: LLMClient) -> None:
		self._llm_client = llm_client

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		messages = [
			{"role": "system", "content": ANALYSIS_PROMPT},
			{
				"role": "user",
				"content": json.dumps(
					{
						"issue_key": context.input_payload["issue_key"],
						"bug_report": context.input_payload["bug_report"],
					},
					ensure_ascii=False,
					indent=2,
				),
			},
		]
		text = await self._llm_client.invoke_text(messages)
		payload = load_json_object(text, "AnalysisStep")
		analysis = {
			"summary": optional_text(payload.get("summary")),
			"symptoms": string_list(payload.get("symptoms")),
			"impacted_components": string_list(payload.get("impacted_components")),
			"suspected_factors": string_list(payload.get("suspected_factors")),
			"evidence": string_list(payload.get("evidence")),
		}
		if not analysis["summary"]:
			raise ValueError("AnalysisStep produced an empty summary.")
		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="analysis",
			artifact=analysis,
		)


class RootCauseStep:
	name = "root_cause"

	def __init__(self, llm_client: LLMClient) -> None:
		self._llm_client = llm_client

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		messages = [
			{"role": "system", "content": ROOT_CAUSE_PROMPT},
			{
				"role": "user",
				"content": json.dumps(
					{
						"issue_key": context.input_payload["issue_key"],
						"bug_report": context.input_payload["bug_report"],
						"analysis": context.artifacts["analysis"],
					},
					ensure_ascii=False,
					indent=2,
				),
			},
		]
		text = await self._llm_client.invoke_text(messages)
		payload = load_json_object(text, "RootCauseStep")
		root_cause = {
			"root_cause": optional_text(payload.get("root_cause")),
			"confidence": optional_text(payload.get("confidence")),
			"reasoning": string_list(payload.get("reasoning")),
			"mitigations": string_list(payload.get("mitigations")),
		}
		if not root_cause["root_cause"]:
			raise ValueError("RootCauseStep produced an empty root cause.")
		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="root_cause",
			artifact=root_cause,
		)


class JiraCommentStep:
	name = "jira_comment"

	def __init__(self, llm_client: LLMClient) -> None:
		self._llm_client = llm_client

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		messages = [
			{"role": "system", "content": JIRA_COMMENT_PROMPT},
			{
				"role": "user",
				"content": json.dumps(
					{
						"issue_key": context.input_payload["issue_key"],
						"bug_report": context.input_payload["bug_report"],
						"analysis": context.artifacts["analysis"],
						"root_cause": context.artifacts["root_cause"],
					},
					ensure_ascii=False,
					indent=2,
				),
			},
		]
		jira_comment = (await self._llm_client.invoke_text(messages)).strip()
		if not jira_comment:
			raise ValueError("JiraCommentStep produced an empty Jira comment.")
		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="jira_comment",
			artifact=jira_comment,
		)


class PostJiraCommentStep:
	name = "post_jira_comment"

	def __init__(self, tool_dispatcher: ToolDispatcher) -> None:
		self._tool_dispatcher = tool_dispatcher

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		if not context.input_payload.get("post_to_jira", False):
			return WorkflowStepOutcome(
				status=WorkflowStepStatus.SKIPPED,
				artifact_key="jira_delivery",
				artifact={
					"posted": False,
					"reason": "post_to_jira_disabled",
				},
			)

		jira_comment = context.artifacts.get("jira_comment")
		if not isinstance(jira_comment, str) or not jira_comment.strip():
			raise ValueError("PostJiraCommentStep requires a jira_comment artifact.")

		issue_key = optional_text(context.input_payload.get("issue_key"))
		result = self._tool_dispatcher.dispatch(
			"post_jira_comment",
			{
				"issue_key": issue_key,
				"comment": jira_comment,
			},
		)
		if result.get("status") == "error":
			return WorkflowStepOutcome(
				status=WorkflowStepStatus.FAILED,
				artifact_key="jira_delivery",
				artifact=result,
				error=str(result.get("error") or "Jira delivery failed."),
			)

		return WorkflowStepOutcome(
			status=WorkflowStepStatus.SUCCESS,
			artifact_key="jira_delivery",
			artifact={
				"posted": True,
				"issue_key": issue_key,
				"tool_result": result,
			},
		)


class BugWorkflow:
	workflow_type = "bug"

	def __init__(
		self,
		llm_client: LLMClient,
		tool_dispatcher: ToolDispatcher,
		runner: WorkflowRunner | None = None,
	) -> None:
		self._runner = runner or WorkflowRunner()
		self._steps = [
			AnalysisStep(llm_client),
			RootCauseStep(llm_client),
			JiraCommentStep(llm_client),
			PostJiraCommentStep(tool_dispatcher),
		]

	async def run(
		self,
		*,
		session_id: str,
		bug_report: str,
		issue_key: str,
		post_to_jira: bool = False,
	) -> WorkflowRunResult:
		workflow_id = f"workflow-{uuid4().hex}"
		context = WorkflowContext(
			workflow_id=workflow_id,
			workflow_type=self.workflow_type,
			session_id=session_id,
			input_payload={
				"bug_report": bug_report,
				"issue_key": issue_key,
				"post_to_jira": post_to_jira,
			},
			artifacts={"bug_report": bug_report},
		)
		return await self._runner.run(self.workflow_type, context, self._steps)