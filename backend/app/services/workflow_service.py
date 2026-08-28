from dataclasses import replace
from datetime import UTC, datetime

from pydantic import BaseModel

from app.llm.client import LLMClient
from app.memory.memory_manager import MemoryManager
from app.services.tool_dispatcher import ToolDispatcher
from app.workflows.base import WorkflowRunResult, WorkflowStepResult, WorkflowStepStatus
from app.workflows.cache_service import WorkflowArtifactCacheService
from app.workflows.registry import WorkflowRegistry, build_default_workflow_registry


class WorkflowService:
	"""Application service for deterministic workflow execution."""

	def __init__(
		self,
		tool_dispatcher: ToolDispatcher | None = None,
		llm_client: LLMClient | None = None,
		memory_manager: MemoryManager | None = None,
		artifact_cache_service: WorkflowArtifactCacheService | None = None,
		workflow_registry: WorkflowRegistry | None = None,
	) -> None:
		self._tool_dispatcher = tool_dispatcher or ToolDispatcher()
		self._llm_client = llm_client or LLMClient()
		self._memory_manager = memory_manager or MemoryManager()
		self._artifact_cache_service = artifact_cache_service or WorkflowArtifactCacheService()
		self._workflow_registry = workflow_registry or build_default_workflow_registry(
			llm_client=self._llm_client,
			memory_manager=self._memory_manager,
			tool_dispatcher=self._tool_dispatcher,
		)
		self._workflow_registry.register_runner("meeting", self._run_registered_meeting_workflow)
		self._workflow_registry.register_runner("bug", self._run_registered_bug_workflow)

	def _now(self) -> datetime:
		return datetime.now(UTC)

	def supported_workflow_types(self) -> tuple[str, ...]:
		return self._workflow_registry.supported_workflow_types()

	def validate_workflow_input(self, workflow_type: str, payload: dict[str, object]) -> BaseModel:
		return self._workflow_registry.validate_input(workflow_type, payload)

	async def run_workflow(
		self,
		workflow_type: str,
		*,
		session_id: str,
		**kwargs: object,
	) -> WorkflowRunResult:
		return await self._workflow_registry.run(workflow_type, session_id=session_id, **kwargs)

	async def _execute_meeting_workflow(
		self,
		*,
		session_id: str,
		transcript: str,
		meeting_title: str | None = None,
		channel: str = "engineering",
		send_to_teams: bool = False,
	) -> WorkflowRunResult:
		workflow = self._workflow_registry.create("meeting")
		return await workflow.run(
			session_id=session_id,
			transcript=transcript,
			meeting_title=meeting_title,
			channel=channel,
			send_to_teams=send_to_teams,
		)

	async def _execute_bug_workflow(
		self,
		*,
		session_id: str,
		bug_report: str,
		issue_key: str,
		post_to_jira: bool = False,
	) -> WorkflowRunResult:
		workflow = self._workflow_registry.create("bug")
		return await workflow.run(
			session_id=session_id,
			bug_report=bug_report,
			issue_key=issue_key,
			post_to_jira=post_to_jira,
		)

	async def _run_registered_meeting_workflow(
		self,
		*,
		session_id: str,
		transcript: str,
		meeting_title: str | None = None,
		channel: str = "engineering",
		send_to_teams: bool = False,
	) -> WorkflowRunResult:
		return await self.run_meeting_workflow(
			session_id=session_id,
			transcript=transcript,
			meeting_title=meeting_title,
			channel=channel,
			send_to_teams=send_to_teams,
		)

	async def _run_registered_bug_workflow(
		self,
		*,
		session_id: str,
		bug_report: str,
		issue_key: str,
		post_to_jira: bool = False,
	) -> WorkflowRunResult:
		return await self.run_bug_workflow(
			session_id=session_id,
			bug_report=bug_report,
			issue_key=issue_key,
			post_to_jira=post_to_jira,
		)

	async def _build_send_teams_step_result(self, *, channel: str, memo: str, send_to_teams: bool) -> tuple[WorkflowStepResult, dict[str, object]]:
		started_at = self._now()
		if not send_to_teams:
			completed_at = self._now()
			artifact = {
				"sent": False,
				"reason": "send_to_teams_disabled",
			}
			return (
				WorkflowStepResult(
					step_name="send_teams",
					status=WorkflowStepStatus.SKIPPED,
					artifact_key="teams_delivery",
					artifact=artifact,
					error=None,
					started_at=started_at,
					completed_at=completed_at,
					duration_ms=round((completed_at - started_at).total_seconds() * 1000, 3),
				),
				artifact,
			)

		result = await self._tool_dispatcher.dispatch(
			"send_teams_message",
			{
				"channel": channel,
				"message": memo,
			},
		)
		completed_at = self._now()
		if result.get("status") == "error":
			artifact = result
			step_status = WorkflowStepStatus.FAILED
			error = str(result.get("error") or "Teams delivery failed.")
		else:
			artifact = {
				"sent": True,
				"channel": channel,
				"tool_result": result,
			}
			step_status = WorkflowStepStatus.SUCCESS
			error = None

		return (
			WorkflowStepResult(
				step_name="send_teams",
				status=step_status,
				artifact_key="teams_delivery",
				artifact=artifact,
				error=error,
				started_at=started_at,
				completed_at=completed_at,
				duration_ms=round((completed_at - started_at).total_seconds() * 1000, 3),
			),
			artifact,
		)

	def _build_cache_hit_result(
		self,
		*,
		cached_result: WorkflowRunResult,
		session_id: str,
		channel: str,
		send_to_teams: bool,
		cache_payload: dict[str, object],
	) -> WorkflowRunResult:
		artifacts = dict(cached_result.artifacts)
		steps = list(cached_result.steps)

		steps.append(
			WorkflowStepResult(
				step_name="save_memory",
				status=WorkflowStepStatus.SKIPPED,
				artifact_key="memory_record",
				artifact={
					"saved": False,
					"reason": "cache_hit_no_replay",
				},
				error=None,
				started_at=self._now(),
				completed_at=self._now(),
				duration_ms=0.0,
			)
		)
		artifacts["memory_record"] = {
			"saved": False,
			"reason": "cache_hit_no_replay",
		}

		memo = artifacts.get("memo")
		if not isinstance(memo, str) or not memo.strip():
			return cached_result.with_session_id(session_id).with_steps(steps).with_artifacts(artifacts).with_cache(cache_payload)

		send_step_result, teams_artifact = self._build_send_teams_step_result(
			channel=channel,
			memo=memo,
			send_to_teams=send_to_teams,
		)
		steps.append(send_step_result)
		artifacts["teams_delivery"] = teams_artifact

		status = cached_result.status
		error = cached_result.error
		if send_step_result.status == WorkflowStepStatus.FAILED:
			status = replace(status, value=status.value) if False else cached_result.status
			error = send_step_result.error

		updated_result = cached_result.with_session_id(session_id).with_steps(steps).with_artifacts(artifacts).with_cache(cache_payload)
		if send_step_result.status == WorkflowStepStatus.FAILED:
			return replace(updated_result, status=type(updated_result.status).FAILED, error=error)
		return updated_result

	async def _build_post_jira_step_result(self, *, issue_key: str, jira_comment: str, post_to_jira: bool) -> tuple[WorkflowStepResult, dict[str, object]]:
		started_at = self._now()
		if not post_to_jira:
			completed_at = self._now()
			artifact = {
				"posted": False,
				"reason": "post_to_jira_disabled",
			}
			return (
				WorkflowStepResult(
					step_name="post_jira_comment",
					status=WorkflowStepStatus.SKIPPED,
					artifact_key="jira_delivery",
					artifact=artifact,
					error=None,
					started_at=started_at,
					completed_at=completed_at,
					duration_ms=round((completed_at - started_at).total_seconds() * 1000, 3),
				),
				artifact,
			)

		result = await self._tool_dispatcher.dispatch(
			"post_jira_comment",
			{
				"issue_key": issue_key,
				"comment": jira_comment,
			},
		)
		completed_at = self._now()
		if result.get("status") == "error":
			artifact = result
			step_status = WorkflowStepStatus.FAILED
			error = str(result.get("error") or "Jira delivery failed.")
		else:
			artifact = {
				"posted": True,
				"issue_key": issue_key,
				"tool_result": result,
			}
			step_status = WorkflowStepStatus.SUCCESS
			error = None

		return (
			WorkflowStepResult(
				step_name="post_jira_comment",
				status=step_status,
				artifact_key="jira_delivery",
				artifact=artifact,
				error=error,
				started_at=started_at,
				completed_at=completed_at,
				duration_ms=round((completed_at - started_at).total_seconds() * 1000, 3),
			),
			artifact,
		)

	def _build_bug_cache_hit_result(
		self,
		*,
		cached_result: WorkflowRunResult,
		session_id: str,
		issue_key: str,
		post_to_jira: bool,
		cache_payload: dict[str, object],
	) -> WorkflowRunResult:
		artifacts = dict(cached_result.artifacts)
		steps = list(cached_result.steps)

		jira_comment = artifacts.get("jira_comment")
		if not isinstance(jira_comment, str) or not jira_comment.strip():
			return cached_result.with_session_id(session_id).with_steps(steps).with_artifacts(artifacts).with_cache(cache_payload)

		jira_step_result, jira_artifact = self._build_post_jira_step_result(
			issue_key=issue_key,
			jira_comment=jira_comment,
			post_to_jira=post_to_jira,
		)
		steps.append(jira_step_result)
		artifacts["jira_delivery"] = jira_artifact

		updated_result = cached_result.with_session_id(session_id).with_steps(steps).with_artifacts(artifacts).with_cache(cache_payload)
		if jira_step_result.status == WorkflowStepStatus.FAILED:
			return replace(updated_result, status=type(updated_result.status).FAILED, error=jira_step_result.error)
		return updated_result

	async def run_meeting_workflow(
		self,
		*,
		session_id: str,
		transcript: str,
		meeting_title: str | None = None,
		channel: str = "engineering",
		send_to_teams: bool = False,
	) -> WorkflowRunResult:
		cache_metadata = self._artifact_cache_service.build_meeting_cache_metadata(
			meeting_title=meeting_title,
			transcript=transcript,
			channel=channel,
			send_to_teams=send_to_teams,
		)
		cache_hit = self._artifact_cache_service.lookup_meeting_result(
			meeting_title=meeting_title,
			transcript=transcript,
			channel=channel,
			send_to_teams=send_to_teams,
		)
		if cache_hit is not None:
			return self._build_cache_hit_result(
				cached_result=cache_hit.result,
				session_id=session_id,
				channel=channel,
				send_to_teams=send_to_teams,
				cache_payload={
					"hit": True,
					"strategy": "normalized_transcript_hash",
					"input_hash": cache_hit.input_hash,
					"normalized_input": cache_hit.normalized_input,
				},
			)

		result = await self._execute_meeting_workflow(
			session_id=session_id,
			transcript=transcript,
			meeting_title=meeting_title,
			channel=channel,
			send_to_teams=send_to_teams,
		)
		if result.status.value == "completed":
			self._artifact_cache_service.store_meeting_result(
				session_id=session_id,
				meeting_title=meeting_title,
				transcript=transcript,
				channel=channel,
				send_to_teams=send_to_teams,
				result=result,
			)
		return result.with_cache(
			{
				"hit": False,
				"strategy": "normalized_transcript_hash",
				"input_hash": str(cache_metadata["input_hash"]),
				"normalized_input": str(cache_metadata["normalized_input"]),
			}
		)

	async def run_bug_workflow(
		self,
		*,
		session_id: str,
		bug_report: str,
		issue_key: str,
		post_to_jira: bool = False,
	) -> WorkflowRunResult:
		cache_metadata = self._artifact_cache_service.build_bug_cache_metadata(
			bug_report=bug_report,
			issue_key=issue_key,
			post_to_jira=post_to_jira,
		)
		cache_hit = self._artifact_cache_service.lookup_bug_result(
			bug_report=bug_report,
			issue_key=issue_key,
			post_to_jira=post_to_jira,
		)
		if cache_hit is not None:
			return self._build_bug_cache_hit_result(
				cached_result=cache_hit.result,
				session_id=session_id,
				issue_key=issue_key,
				post_to_jira=post_to_jira,
				cache_payload={
					"hit": True,
					"strategy": "normalized_bug_report_hash",
					"input_hash": cache_hit.input_hash,
					"normalized_input": cache_hit.normalized_input,
				},
			)

		result = await self._execute_bug_workflow(
			session_id=session_id,
			bug_report=bug_report,
			issue_key=issue_key,
			post_to_jira=post_to_jira,
		)
		if result.status.value == "completed":
			self._artifact_cache_service.store_bug_result(
				session_id=session_id,
				bug_report=bug_report,
				issue_key=issue_key,
				post_to_jira=post_to_jira,
				result=result,
			)
		return result.with_cache(
			{
				"hit": False,
				"strategy": "normalized_bug_report_hash",
				"input_hash": str(cache_metadata["input_hash"]),
				"normalized_input": str(cache_metadata["normalized_input"]),
			}
		)