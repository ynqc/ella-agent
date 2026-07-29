import unittest
from datetime import UTC, datetime

from pydantic import BaseModel

from app.agent.workflow_clarification_store import WorkflowClarificationStore
from app.agent.state import AgentPhase, AgentRunResult, AgentState
from app.agent.workflow_planner import WorkflowClarification, WorkflowPlan
from app.services.chat_service import ChatService
from app.workflows.base import WorkflowRunResult, WorkflowRunStatus
from app.workflows.contracts import BugWorkflowInput, MeetingWorkflowInput


class StubChatAgent:
	def __init__(self) -> None:
		self.run_calls = []
		self.stream_calls = []

	async def run(self, session_id: str, message: str) -> AgentRunResult:
		self.run_calls.append((session_id, message))
		state = AgentState(session_id=session_id, user_message=message)
		state.phase = AgentPhase.COMPLETED
		state.final_text = f"chat:{message}"
		state.final_chunks = [state.final_text]
		state.completed_at = datetime.now(UTC)
		return AgentRunResult(state=state, output=state.final_text)

	async def stream_response(self, session_id: str, message: str):
		self.stream_calls.append((session_id, message))
		yield f"chat:{message}"


class StubWorkflowPlanner:
	def __init__(
		self,
		plan: WorkflowPlan | WorkflowClarification | None,
		resolved_plan: WorkflowPlan | WorkflowClarification | None = None,
	) -> None:
		self.plan_result = plan
		self.resolved_plan = resolved_plan
		self.messages = []
		self.resolve_calls = []

	async def plan(self, message: str) -> WorkflowPlan | WorkflowClarification | None:
		self.messages.append(message)
		return self.plan_result

	async def resolve_clarification(
		self,
		*,
		clarification: WorkflowClarification,
		original_message: str,
		followup_message: str,
	) -> WorkflowPlan | WorkflowClarification | None:
		self.resolve_calls.append((clarification, original_message, followup_message))
		return self.resolved_plan


class StubWorkflowService:
	def __init__(self, result: WorkflowRunResult) -> None:
		self.result = result
		self.calls = []
		self.input_models: dict[str, type[BaseModel]] = {
			"meeting": MeetingWorkflowInput,
			"bug": BugWorkflowInput,
		}

	def validate_workflow_input(self, workflow_type: str, payload: dict[str, object]) -> BaseModel:
		return self.input_models[workflow_type.strip()].model_validate(payload)

	async def run_workflow(self, workflow_type: str, *, session_id: str, **kwargs: object) -> WorkflowRunResult:
		self.calls.append((workflow_type, session_id, kwargs))
		return self.result


def workflow_result(*, workflow_type: str, artifacts: dict[str, object], cache_hit: bool) -> WorkflowRunResult:
	now = datetime.now(UTC)
	return WorkflowRunResult(
		workflow_id="workflow-test",
		workflow_type=workflow_type,
		session_id="session-test",
		status=WorkflowRunStatus.COMPLETED,
		steps=[],
		artifacts=artifacts,
		started_at=now,
		completed_at=now,
		cache={"hit": cache_hit},
	)


class ChatServiceTests(unittest.IsolatedAsyncioTestCase):
	async def test_run_response_falls_back_to_chat(self) -> None:
		agent = StubChatAgent()
		service = ChatService(
			agent=agent,
			workflow_service=StubWorkflowService(workflow_result(workflow_type="meeting", artifacts={}, cache_hit=False)),
			workflow_planner=StubWorkflowPlanner(None),
		)

		result = await service.run_response("session-1", "你好")

		self.assertEqual(result.output, "chat:你好")
		self.assertEqual(agent.run_calls, [("session-1", "你好")])

	async def test_run_response_routes_meeting_workflow(self) -> None:
		agent = StubChatAgent()
		workflow_service = StubWorkflowService(
			workflow_result(
				workflow_type="meeting",
				artifacts={
					"memo": "# Weekly Sync\n\nSummary",
					"teams_delivery": {"sent": True},
				},
				cache_hit=True,
			)
		)
		service = ChatService(
			agent=agent,
			workflow_service=workflow_service,
			workflow_planner=StubWorkflowPlanner(
				WorkflowPlan(
					workflow_type="meeting",
					input_payload={
						"transcript": "会议纪要原文",
						"meeting_title": "Weekly Sync",
						"channel": "engineering",
						"send_to_teams": True,
					},
					rationale="meeting summary request",
				)
			),
		)

		result = await service.run_response("session-2", "帮我总结会议纪要并发 Teams")

		self.assertEqual(agent.run_calls, [])
		self.assertEqual(workflow_service.calls[0][0], "meeting")
		self.assertIn("已执行 meeting workflow", result.output)
		self.assertIn("缓存：命中", result.output)
		self.assertIn("# Weekly Sync", result.output)
		self.assertEqual(result.state.phase.value, "completed")
		self.assertIn('"workflow_type": "meeting"', result.state.planning_text)
		self.assertEqual(result.state.planner_result["route"], "workflow")
		self.assertEqual(result.state.workflow_execution["workflow_type"], "meeting")
		self.assertTrue(result.state.workflow_execution["cache"]["hit"])

	async def test_stream_response_routes_bug_workflow(self) -> None:
		agent = StubChatAgent()
		workflow_service = StubWorkflowService(
			workflow_result(
				workflow_type="bug",
				artifacts={
					"jira_comment": "Summary\n\nInvestigated checkout failure.",
					"jira_delivery": {"posted": False, "reason": "post_to_jira_disabled"},
				},
				cache_hit=False,
			)
		)
		service = ChatService(
			agent=agent,
			workflow_service=workflow_service,
			workflow_planner=StubWorkflowPlanner(
				WorkflowPlan(
					workflow_type="bug",
					input_payload={
						"bug_report": "Checkout returns 500 after deployment.",
						"issue_key": "BUG-123",
						"post_to_jira": False,
					},
					rationale="bug analysis request",
				)
			),
		)

		chunks = []
		async for chunk in service.stream_response("session-3", "分析这个 bug 并生成 Jira comment"):
			chunks.append(chunk)

		self.assertEqual(agent.stream_calls, [])
		self.assertEqual(workflow_service.calls[0][0], "bug")
		self.assertEqual(len(chunks), 1)
		self.assertIn("已执行 bug workflow", chunks[0])
		self.assertIn("Jira：未发送评论", chunks[0])

	async def test_run_response_returns_clarification_for_missing_workflow_input(self) -> None:
		agent = StubChatAgent()
		workflow_service = StubWorkflowService(
			workflow_result(workflow_type="bug", artifacts={}, cache_hit=False)
		)
		service = ChatService(
			agent=agent,
			workflow_service=workflow_service,
			workflow_planner=StubWorkflowPlanner(
				WorkflowClarification(
					workflow_type="bug",
					missing_fields=["issue_key"],
					message="要继续生成 Jira comment，我还需要 issue key，例如 BUG-123。",
					rationale="missing bug issue key",
				)
			),
		)

		result = await service.run_response("session-4", "帮我分析这个 bug 并发 Jira comment")

		self.assertEqual(agent.run_calls, [])
		self.assertEqual(workflow_service.calls, [])
		self.assertEqual(result.output, "要继续生成 Jira comment，我还需要 issue key，例如 BUG-123。")
		self.assertIn('"route": "clarify"', result.state.planning_text)
		self.assertIn('"missing_fields": ["issue_key"]', result.state.planning_text)
		self.assertEqual(
			result.state.pending_workflow_clarification,
			{
				"workflow_type": "bug",
				"missing_fields": ["issue_key"],
				"clarification_message": "要继续生成 Jira comment，我还需要 issue key，例如 BUG-123。",
				"input": {},
				"rationale": "missing bug issue key",
			},
		)
		self.assertEqual(result.state.planner_result["route"], "clarify")

	async def test_run_response_resolves_pending_clarification_and_executes_workflow(self) -> None:
		agent = StubChatAgent()
		workflow_service = StubWorkflowService(
			workflow_result(
				workflow_type="bug",
				artifacts={
					"jira_comment": "Summary\n\nInvestigated checkout failure.",
					"jira_delivery": {"posted": True},
				},
				cache_hit=False,
			)
		)
		planner = StubWorkflowPlanner(
			WorkflowClarification(
				workflow_type="bug",
				missing_fields=["issue_key"],
				message="要继续生成 Jira comment，我还需要 issue key，例如 BUG-123。",
				input_payload={
					"bug_report": "Checkout returns 500 after deployment.",
					"post_to_jira": True,
				},
				rationale="missing bug issue key",
			),
			resolved_plan=WorkflowPlan(
				workflow_type="bug",
				input_payload={
					"issue_key": "BUG-123",
				},
				rationale="clarification completed",
			),
		)
		store = WorkflowClarificationStore()
		service = ChatService(
			agent=agent,
			workflow_service=workflow_service,
			workflow_planner=planner,
			workflow_clarification_store=store,
		)

		first = await service.run_response("session-5", "帮我分析这个 bug 并发 Jira comment")
		second = await service.run_response("session-5", "BUG-123")

		self.assertEqual(first.output, "要继续生成 Jira comment，我还需要 issue key，例如 BUG-123。")
		self.assertEqual(len(planner.resolve_calls), 1)
		self.assertEqual(planner.resolve_calls[0][1], "帮我分析这个 bug 并发 Jira comment")
		self.assertEqual(planner.resolve_calls[0][2], "BUG-123")
		self.assertEqual(workflow_service.calls[0][0], "bug")
		self.assertEqual(workflow_service.calls[0][2]["issue_key"], "BUG-123")
		self.assertEqual(workflow_service.calls[0][2]["bug_report"], "Checkout returns 500 after deployment.")
		self.assertTrue(workflow_service.calls[0][2]["post_to_jira"])
		self.assertIn("已执行 bug workflow", second.output)
		self.assertEqual(
			second.state.pending_workflow_clarification,
			{
				"workflow_type": "bug",
				"missing_fields": ["issue_key"],
				"clarification_message": "要继续生成 Jira comment，我还需要 issue key，例如 BUG-123。",
				"input": {
					"bug_report": "Checkout returns 500 after deployment.",
					"post_to_jira": True,
				},
				"original_message": "帮我分析这个 bug 并发 Jira comment",
				"rationale": "missing bug issue key",
			},
		)
		self.assertIsNone(store.get("session-5"))

	async def test_run_response_discards_pending_clarification_on_topic_switch(self) -> None:
		agent = StubChatAgent()
		workflow_service = StubWorkflowService(
			workflow_result(workflow_type="bug", artifacts={}, cache_hit=False)
		)
		planner = StubWorkflowPlanner(
			None,
			resolved_plan=None,
		)
		store = WorkflowClarificationStore()
		store.set(
			"session-6",
			WorkflowClarification(
				workflow_type="bug",
				missing_fields=["issue_key"],
				message="要继续生成 Jira comment，我还需要 issue key，例如 BUG-123。",
				input_payload={
					"bug_report": "Checkout returns 500 after deployment.",
					"post_to_jira": True,
				},
				rationale="missing bug issue key",
			),
			"帮我分析这个 bug 并发 Jira comment",
		)
		service = ChatService(
			agent=agent,
			workflow_service=workflow_service,
			workflow_planner=planner,
			workflow_clarification_store=store,
		)

		result = await service.run_response("session-6", "先别管那个 bug 了，解释下 AirflowSkipException")

		self.assertEqual(result.output, "chat:先别管那个 bug 了，解释下 AirflowSkipException")
		self.assertEqual(len(planner.resolve_calls), 1)
		self.assertEqual(planner.messages, ["先别管那个 bug 了，解释下 AirflowSkipException"])
		self.assertEqual(agent.run_calls, [("session-6", "先别管那个 bug 了，解释下 AirflowSkipException")])
		self.assertEqual(workflow_service.calls, [])
		self.assertIsNone(store.get("session-6"))

	async def test_run_response_surfaces_workflow_validation_failure(self) -> None:
		agent = StubChatAgent()
		workflow_service = StubWorkflowService(
			workflow_result(workflow_type="meeting", artifacts={}, cache_hit=False)
		)
		service = ChatService(
			agent=agent,
			workflow_service=workflow_service,
			workflow_planner=StubWorkflowPlanner(
				WorkflowPlan(
					workflow_type="meeting",
					input_payload={
						"meeting_title": "Weekly Sync",
					},
					rationale="meeting summary request",
				)
			),
		)

		result = await service.run_response("session-7", "帮我整理会议")

		self.assertEqual(agent.run_calls, [])
		self.assertEqual(workflow_service.calls, [])
		self.assertEqual(result.state.phase, AgentPhase.FAILED)
		self.assertEqual(result.state.planner_result["route"], "workflow")
		self.assertEqual(result.state.workflow_execution["status"], "not_run")
		self.assertEqual(result.state.workflow_validation_error["workflow_type"], "meeting")
		self.assertIn("transcript", result.output)