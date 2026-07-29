import unittest

from app.agent.workflow_planner import WorkflowClarification, WorkflowPlan, WorkflowPlanner


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