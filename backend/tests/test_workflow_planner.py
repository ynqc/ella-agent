import unittest

from app.agent.workflow_planner import WorkflowClarification, WorkflowIntent, WorkflowPlan, WorkflowPlanner


class StubLLMClient:
	def __init__(self, responses: list[str]) -> None:
		self._responses = responses
		self.calls: list[list[dict[str, str]]] = []

	async def invoke_text(self, messages: list[dict[str, str]]) -> str:
		self.calls.append(messages)
		if not self._responses:
			raise AssertionError("No stub LLM response available")
		return self._responses.pop(0)


class WorkflowPlannerParsingTests(unittest.TestCase):
	def setUp(self) -> None:
		self.planner = WorkflowPlanner(llm_client=None)

	def test_parse_plan_payload_filters_unknown_workflow_input_fields(self) -> None:
		result = self.planner._parse_plan_payload(
			{
				"route": "workflow",
				"workflow_type": "meeting",
				"input": {
					"transcript": "Weekly sync transcript",
					"meeting_title": "Weekly Sync",
					"send_to_teams": True,
					"unexpected": "drop me",
				},
				"rationale": "meeting summary request",
			}
		)

		self.assertIsInstance(result, WorkflowPlan)
		assert isinstance(result, WorkflowPlan)
		self.assertEqual(
			result.input_payload,
			{
				"transcript": "Weekly sync transcript",
				"meeting_title": "Weekly Sync",
				"send_to_teams": True,
			},
		)

	def test_parse_clarification_filters_unknown_fields_and_missing_fields(self) -> None:
		result = self.planner._parse_plan_payload(
			{
				"route": "clarify",
				"workflow_type": "bug",
				"input": {
					"bug_report": "Checkout returns 500 after deployment.",
					"issue_key": "BUG-123",
					"unknown": "drop me",
				},
				"missing_fields": ["issue_key", "unknown", ""],
				"clarification_message": "Need the Jira issue key.",
				"rationale": "missing issue key",
			}
		)

		self.assertIsInstance(result, WorkflowClarification)
		assert isinstance(result, WorkflowClarification)
		self.assertEqual(
			result.input_payload,
			{
				"bug_report": "Checkout returns 500 after deployment.",
				"issue_key": "BUG-123",
			},
		)
		self.assertEqual(result.missing_fields, ["issue_key"])
		self.assertEqual(result.message, "要继续执行 bug workflow，我还需要Jira issue key，例如 BUG-123。")

	def test_parse_workflow_payload_with_missing_required_field_downgrades_to_clarify(self) -> None:
		result = self.planner._parse_plan_payload(
			{
				"route": "workflow",
				"workflow_type": "meeting",
				"input": {
					"meeting_title": "Weekly Sync",
					"send_to_teams": True,
				},
				"rationale": "meeting summary request",
			}
		)

		self.assertIsInstance(result, WorkflowClarification)
		assert isinstance(result, WorkflowClarification)
		self.assertEqual(result.workflow_type, "meeting")
		self.assertEqual(result.missing_fields, ["transcript"])
		self.assertEqual(result.input_payload, {"meeting_title": "Weekly Sync", "send_to_teams": True})
		self.assertEqual(result.message, "要继续执行 meeting workflow，我还需要会议 transcript 或会议纪要原文。")

	def test_parse_clarification_infers_missing_required_field_when_llm_omits_it(self) -> None:
		result = self.planner._parse_plan_payload(
			{
				"route": "clarify",
				"workflow_type": "bug",
				"input": {
					"post_to_jira": True,
				},
				"missing_fields": [],
				"clarification_message": "",
				"rationale": "need more info",
			}
		)

		self.assertIsInstance(result, WorkflowClarification)
		assert isinstance(result, WorkflowClarification)
		self.assertEqual(result.missing_fields, ["bug_report", "issue_key"])
		self.assertEqual(
			result.message,
			"要继续执行 bug workflow，我还需要这些信息：bug report 的具体描述、Jira issue key，例如 BUG-123。",
		)

	def test_parse_intent_payload_returns_workflow_intent(self) -> None:
		result = self.planner._parse_intent_payload(
			{
				"route": "workflow",
				"workflow_type": "meeting",
				"rationale": "meeting summary request",
			}
		)

		self.assertIsInstance(result, WorkflowIntent)
		assert isinstance(result, WorkflowIntent)
		self.assertEqual(result.workflow_type, "meeting")
		self.assertEqual(result.rationale, "meeting summary request")


class WorkflowPlannerExecutionTests(unittest.IsolatedAsyncioTestCase):
	async def test_plan_uses_classification_then_slot_filling(self) -> None:
		llm_client = StubLLMClient(
			[
				'{"route":"workflow","workflow_type":"meeting","rationale":"meeting request"}',
				'{"route":"workflow","input":{"transcript":"Weekly sync transcript","meeting_title":"Weekly Sync"},"missing_fields":[],"rationale":"filled slots"}',
			]
		)
		planner = WorkflowPlanner(llm_client=llm_client)

		result = await planner.plan("帮我总结这个会议纪要")

		self.assertIsInstance(result, WorkflowPlan)
		assert isinstance(result, WorkflowPlan)
		self.assertEqual(result.workflow_type, "meeting")
		self.assertEqual(result.input_payload["transcript"], "Weekly sync transcript")
		self.assertEqual(len(llm_client.calls), 2)
		self.assertIn("workflow intent classifier", llm_client.calls[0][0]["content"])
		self.assertIn("extracting workflow input fields", llm_client.calls[1][0]["content"])

	async def test_plan_returns_chat_without_slot_filling_when_intent_is_chat(self) -> None:
		llm_client = StubLLMClient([
			'{"route":"chat","workflow_type":"","rationale":"general question"}'
		])
		planner = WorkflowPlanner(llm_client=llm_client)

		result = await planner.plan("解释一下 AirflowSkipException")

		self.assertIsNone(result)
		self.assertEqual(len(llm_client.calls), 1)

	async def test_bug_search_requests_stay_in_chat(self) -> None:
		llm_client = StubLLMClient([
			'{"route":"chat","workflow_type":"","rationale":"jira search request"}'
		])
		planner = WorkflowPlanner(llm_client=llm_client)

		result = await planner.plan("帮我查一下 Jira 里和 login bug 相关的 issue")

		self.assertIsNone(result)
		self.assertEqual(len(llm_client.calls), 1)
		self.assertIn("Requests to merely search, list, fetch, look up, or query Jira bugs/issues/PRs should stay in normal chat", llm_client.calls[0][0]["content"])

	async def test_resolve_clarification_uses_slot_resolution_only(self) -> None:
		llm_client = StubLLMClient([
			'{"route":"workflow","input":{"issue_key":"BUG-123"},"missing_fields":[],"rationale":"resolved"}'
		])
		planner = WorkflowPlanner(llm_client=llm_client)

		result = await planner.resolve_clarification(
			clarification=WorkflowClarification(
				workflow_type="bug",
				missing_fields=["issue_key"],
				message="要继续执行 bug workflow，我还需要Jira issue key，例如 BUG-123。",
				input_payload={"bug_report": "Checkout returns 500 after deployment."},
				rationale="missing issue_key",
			),
			original_message="帮我分析这个 bug 并发 Jira comment",
			followup_message="BUG-123",
		)

		self.assertIsInstance(result, WorkflowPlan)
		assert isinstance(result, WorkflowPlan)
		self.assertEqual(result.workflow_type, "bug")
		self.assertEqual(result.input_payload, {"issue_key": "BUG-123"})
		self.assertEqual(len(llm_client.calls), 1)
		self.assertIn("resolving missing workflow inputs", llm_client.calls[0][0]["content"])