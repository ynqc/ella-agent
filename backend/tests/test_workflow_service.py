import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")

from pydantic import ValidationError

from app.memory.database import init_db
from app.services.workflow_service import WorkflowService
from app.workflows.cache_service import WorkflowArtifactCacheService


class FakeLLMClient:
	def __init__(self) -> None:
		self.calls = 0

	async def invoke_text(self, messages):
		self.calls += 1
		system = messages[0]["content"]
		if "SummaryStep" in system:
			return '{"title":"Weekly Sync","summary":"Team reviewed release blockers.","key_points":["Reviewed blockers"],"decisions":["Delay launch by 2 days"],"risks":["QA backlog"],"open_questions":["Owner for final signoff"]}'
		if "ActionItemStep" in system:
			return '{"action_items":[{"title":"Close QA backlog","owner":"Alice","due_date":"2026-07-30","status":"open","notes":"Coordinate with QA"}]}'
		if "MemoStep" in system:
			return '# Weekly Sync\n\n## Summary\nTeam reviewed release blockers.\n\n## Action Items\n- Alice: Close QA backlog by 2026-07-30'
		if "AnalysisStep" in system:
			return '{"summary":"Checkout failed for some users.","symptoms":["500 on checkout"],"impacted_components":["payments"],"suspected_factors":["timeout"],"evidence":["production logs"]}'
		if "RootCauseStep" in system:
			return '{"root_cause":"Payment gateway timeout handling regressed.","confidence":"medium","reasoning":["started after deploy"],"mitigations":["rollback timeout change"]}'
		if "JiraCommentStep" in system:
			return 'Summary\n\nInvestigated checkout failure.'
		raise AssertionError("Unexpected prompt")


class FakeMemoryManager:
	def __init__(self) -> None:
		self.saved = []

	def remember(self, session_id, memory_type, content, keywords=None):
		self.saved.append((session_id, memory_type, content, keywords))


class FakeToolDispatcher:
	def __init__(self) -> None:
		self.calls = []

	def dispatch(self, tool_name, params=None):
		self.calls.append((tool_name, params or {}))
		return {
			"tool": tool_name,
			"status": "success",
			"input": params or {},
			"data": [{"delivery_id": f"{tool_name}-123456", "status": "sent"}],
			"error": None,
		}


class WorkflowServiceTests(unittest.IsolatedAsyncioTestCase):
	async def asyncSetUp(self) -> None:
		init_db()
		self.llm = FakeLLMClient()
		self.memory = FakeMemoryManager()
		self.tools = FakeToolDispatcher()
		self.service = WorkflowService(
			tool_dispatcher=self.tools,
			llm_client=self.llm,
			memory_manager=self.memory,
			artifact_cache_service=WorkflowArtifactCacheService(),
		)

	async def test_supported_workflow_types(self) -> None:
		self.assertEqual(self.service.supported_workflow_types(), ("meeting", "bug"))

	async def test_meeting_workflow_cache_semantics(self) -> None:
		first = await self.service.run_meeting_workflow(
			session_id="session-1",
			transcript="Alice owns QA backlog.\r\n\r\nTeam delays launch by 2 days.",
			meeting_title="Weekly Sync",
			channel="engineering",
			send_to_teams=False,
		)
		second = await self.service.run_meeting_workflow(
			session_id="session-2",
			transcript="  Alice owns QA backlog.\n\n\nTeam delays launch by 2 days.  ",
			meeting_title="Weekly Sync",
			channel="engineering",
			send_to_teams=True,
		)

		self.assertFalse(first.cache["hit"])
		self.assertTrue(second.cache["hit"])
		self.assertEqual(self.llm.calls, 3)
		self.assertEqual(len(self.memory.saved), 1)
		self.assertEqual(self.tools.calls[0][0], "send_teams_message")
		self.assertEqual(second.artifacts["memory_record"], {"saved": False, "reason": "cache_hit_no_replay"})
		self.assertTrue(second.artifacts["teams_delivery"]["sent"])

	async def test_generic_meeting_dispatch_preserves_cache_semantics(self) -> None:
		first = await self.service.run_workflow(
			"meeting",
			session_id="session-10",
			transcript="Roadmap review.\n\nAction: Alice updates plan.",
			meeting_title="Roadmap Review",
			channel="product",
			send_to_teams=False,
		)
		second = await self.service.run_workflow(
			"meeting",
			session_id="session-11",
			transcript="  Roadmap review.\n\n\nAction: Alice updates plan.  ",
			meeting_title="Roadmap Review",
			channel="product",
			send_to_teams=True,
		)

		self.assertFalse(first.cache["hit"])
		self.assertTrue(second.cache["hit"])
		self.assertEqual(second.artifacts["memory_record"], {"saved": False, "reason": "cache_hit_no_replay"})
		self.assertTrue(second.artifacts["teams_delivery"]["sent"])

	async def test_run_workflow_dispatches_bug_workflow(self) -> None:
		result = await self.service.run_workflow(
			"bug",
			session_id="session-3",
			bug_report="Checkout returns 500 after deployment.",
			issue_key="BUG-123",
			post_to_jira=True,
		)

		self.assertEqual(result.workflow_type, "bug")
		self.assertEqual(result.status.value, "completed")
		self.assertEqual(self.tools.calls[0][0], "post_jira_comment")

	async def test_run_workflow_normalizes_workflow_type(self) -> None:
		result = await self.service.run_workflow(
			"  meeting  ",
			session_id="session-30",
			transcript="Weekly sync transcript",
			meeting_title="Weekly Sync",
			channel="engineering",
			send_to_teams=False,
		)

		self.assertEqual(result.workflow_type, "meeting")
		self.assertFalse(result.cache["hit"])

	async def test_run_workflow_rejects_blank_workflow_type(self) -> None:
		with self.assertRaisesRegex(ValueError, "Workflow type must be a non-empty string"):
			await self.service.run_workflow(
				"   ",
				session_id="session-31",
			)

	async def test_validate_workflow_input_normalizes_workflow_type(self) -> None:
		validated = self.service.validate_workflow_input(
			"  meeting  ",
			{
				"transcript": "Weekly sync transcript",
				"meeting_title": "Weekly Sync",
				"channel": "engineering",
				"send_to_teams": False,
			},
		)

		self.assertEqual(validated.transcript, "Weekly sync transcript")

	async def test_validate_workflow_input_rejects_invalid_payload(self) -> None:
		with self.assertRaises(ValidationError):
			self.service.validate_workflow_input(
				"meeting",
				{
					"meeting_title": "Weekly Sync",
				},
			)

	async def test_bug_workflow_cache_semantics(self) -> None:
		first = await self.service.run_bug_workflow(
			session_id="session-20",
			bug_report="Checkout returns 500 after deployment.\n\nLogs show timeout spikes.",
			issue_key="BUG-123",
			post_to_jira=False,
		)
		second = await self.service.run_bug_workflow(
			session_id="session-21",
			bug_report="  Checkout returns 500 after deployment.\n\n\nLogs show timeout spikes.  ",
			issue_key="BUG-123",
			post_to_jira=True,
		)

		self.assertFalse(first.cache["hit"])
		self.assertTrue(second.cache["hit"])
		self.assertEqual(second.cache["strategy"], "normalized_bug_report_hash")
		self.assertEqual(self.llm.calls, 3)
		self.assertEqual(self.tools.calls[-1][0], "post_jira_comment")
		self.assertTrue(second.artifacts["jira_delivery"]["posted"])