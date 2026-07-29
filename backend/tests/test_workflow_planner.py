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