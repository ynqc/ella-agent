import unittest
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.dependencies import get_workflow_service
from app.api.workflows import router
from app.services.workflow_service import WorkflowService
from app.workflows.base import WorkflowRunResult, WorkflowRunStatus
from app.workflows.contracts import BugWorkflowInput, MeetingWorkflowInput


class StubWorkflowService(WorkflowService):
	def __init__(self) -> None:
		self.calls = []
		self.input_models: dict[str, type[BaseModel]] = {
			"meeting": MeetingWorkflowInput,
			"bug": BugWorkflowInput,
		}

	def supported_workflow_types(self) -> tuple[str, ...]:
		return ("meeting", "bug")

	def validate_workflow_input(self, workflow_type: str, payload: dict[str, object]) -> BaseModel:
		return self.input_models[workflow_type.strip()].model_validate(payload)

	async def run_workflow(self, workflow_type: str, *, session_id: str, **kwargs: object) -> WorkflowRunResult:
		self.calls.append((workflow_type, session_id, kwargs))
		now = datetime.now(UTC)
		return WorkflowRunResult(
			workflow_id="workflow-test",
			workflow_type=workflow_type,
			session_id=session_id,
			status=WorkflowRunStatus.COMPLETED,
			steps=[],
			artifacts={"echo": kwargs},
			started_at=now,
			completed_at=now,
			error=None,
			cache=None,
		)


class WorkflowApiTests(unittest.TestCase):
	def setUp(self) -> None:
		self.service = StubWorkflowService()
		app = FastAPI()
		app.include_router(router)
		app.dependency_overrides[get_workflow_service] = lambda: self.service
		self.client = TestClient(app)

	def test_generic_run_endpoint_accepts_meeting_workflow(self) -> None:
		response = self.client.post(
			"/api/workflows/run",
			json={
				"workflow_type": "meeting",
				"session_id": "session-123",
				"input": {
					"transcript": "Weekly sync transcript",
					"meeting_title": "Weekly Sync",
					"channel": "engineering",
					"send_to_teams": True,
				},
			},
		)

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["workflow_type"], "meeting")
		self.assertEqual(self.service.calls[0][0], "meeting")
		self.assertEqual(self.service.calls[0][2]["transcript"], "Weekly sync transcript")

	def test_generic_run_endpoint_normalizes_workflow_type(self) -> None:
		response = self.client.post(
			"/api/workflows/run",
			json={
				"workflow_type": "  meeting  ",
				"session_id": "session-124",
				"input": {
					"transcript": "Weekly sync transcript",
					"meeting_title": "Weekly Sync",
					"channel": "engineering",
					"send_to_teams": False,
				},
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.service.calls[-1][0], "meeting")

	def test_legacy_meeting_endpoint_is_removed(self) -> None:
		response = self.client.post(
			"/api/workflows/meeting",
			json={
				"session_id": "session-legacy",
				"transcript": "Weekly sync transcript",
				"meeting_title": "Weekly Sync",
				"channel": "engineering",
				"send_to_teams": False,
			},
		)

		self.assertEqual(response.status_code, 404)
		self.assertEqual(self.service.calls, [])

	def test_generic_run_endpoint_rejects_unsupported_workflow(self) -> None:
		response = self.client.post(
			"/api/workflows/run",
			json={
				"workflow_type": "unknown",
				"input": {},
			},
		)

		self.assertEqual(response.status_code, 400)
		payload = response.json()
		self.assertIn("supported_workflow_types", payload["detail"])

	def test_legacy_bug_endpoint_is_removed(self) -> None:
		response = self.client.post(
			"/api/workflows/bug",
			json={
				"session_id": "session-bug",
				"bug_report": "Checkout returns 500 after deployment.",
				"issue_key": "BUG-123",
				"post_to_jira": True,
			},
		)

		self.assertEqual(response.status_code, 404)
		self.assertEqual(self.service.calls, [])

	def test_generic_run_endpoint_validates_workflow_input(self) -> None:
		response = self.client.post(
			"/api/workflows/run",
			json={
				"workflow_type": "meeting",
				"input": {
					"meeting_title": "Weekly Sync"
				},
			},
		)

		self.assertEqual(response.status_code, 422)
		payload = response.json()
		self.assertEqual(payload["detail"]["workflow_type"], "meeting")
		self.assertEqual(payload["detail"]["message"], "Invalid input for workflow_type: meeting")
		self.assertEqual(payload["detail"]["errors"][0]["field"], "transcript")
		self.assertIn("required", payload["detail"]["errors"][0]["message"].lower())