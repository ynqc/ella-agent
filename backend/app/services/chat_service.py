from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json

from pydantic import ValidationError

from app.agent.chat_agent import ChatAgent
from app.agent.state import AgentPhase, AgentRunResult, AgentState
from app.agent.workflow_clarification_store import WorkflowClarificationStore
from app.agent.workflow_planner import WorkflowClarification, WorkflowPlan, WorkflowPlanner
from app.services.workflow_service import WorkflowService
from app.workflows.base import WorkflowRunResult


class ChatService:
	"""Application service for chat requests."""

	def __init__(
		self,
		agent: ChatAgent | None = None,
		workflow_service: WorkflowService | None = None,
		workflow_planner: WorkflowPlanner | None = None,
		workflow_clarification_store: WorkflowClarificationStore | None = None,
	) -> None:
		self._agent = agent or ChatAgent()
		self._workflow_service = workflow_service or WorkflowService()
		self._workflow_planner = workflow_planner or WorkflowPlanner()
		self._workflow_clarification_store = workflow_clarification_store or WorkflowClarificationStore()

	def _now(self) -> datetime:
		return datetime.now(UTC)

	def _format_workflow_output(self, plan: WorkflowPlan, result: WorkflowRunResult) -> str:
		cache_hit = False if result.cache is None else bool(result.cache.get("hit", False))
		cache_text = "命中" if cache_hit else "未命中"
		if plan.workflow_type == "meeting":
			memo = result.artifacts.get("memo")
			teams_delivery = result.artifacts.get("teams_delivery")
			lines = ["已执行 meeting workflow。", f"缓存：{cache_text}。"]
			if isinstance(teams_delivery, dict):
				if teams_delivery.get("sent") is True:
					lines.append("Teams：已发送。")
				elif teams_delivery.get("reason") == "send_to_teams_disabled":
					lines.append("Teams：未发送。")
				elif teams_delivery.get("sent") is False:
					lines.append("Teams：跳过。")
			if isinstance(memo, str) and memo.strip():
				lines.extend(["", memo])
			return "\n".join(lines)

		if plan.workflow_type == "bug":
			jira_comment = result.artifacts.get("jira_comment")
			jira_delivery = result.artifacts.get("jira_delivery")
			lines = ["已执行 bug workflow。", f"缓存：{cache_text}。"]
			if isinstance(jira_delivery, dict):
				if jira_delivery.get("posted") is True:
					lines.append("Jira：已发送评论。")
				elif jira_delivery.get("reason") == "post_to_jira_disabled":
					lines.append("Jira：未发送评论。")
				elif jira_delivery.get("posted") is False:
					lines.append("Jira：跳过。")
			if isinstance(jira_comment, str) and jira_comment.strip():
				lines.extend(["", jira_comment])
			return "\n".join(lines)

		return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

	def _build_workflow_run_result(
		self,
		*,
		session_id: str,
		message: str,
		plan: WorkflowPlan,
		workflow_result: WorkflowRunResult,
		pending_clarification: dict[str, object] | None = None,
	) -> AgentRunResult:
		state = AgentState(session_id=session_id, user_message=message.strip())
		now = self._now()
		state.phase = AgentPhase.COMPLETED
		state.last_phase_started_at = now
		state.completed_at = now
		state.planning_text = WorkflowPlanner.serialize_plan(plan)
		state.planner_result = self._serialize_planner_result(plan)
		state.pending_workflow_clarification = pending_clarification
		state.workflow_execution = {
			"workflow_id": workflow_result.workflow_id,
			"workflow_type": workflow_result.workflow_type,
			"input": plan.input_payload,
			"status": workflow_result.status.value,
			"cache": workflow_result.cache,
		}
		state.final_text = self._format_workflow_output(plan, workflow_result)
		state.final_chunks = [state.final_text]
		state.phase_durations_ms = {
			AgentPhase.PLANNING.value: 0.0,
			AgentPhase.COMPLETED.value: 0.0,
		}
		return AgentRunResult(state=state, output=state.final_text)

	def _serialize_planner_result(self, plan: WorkflowPlan | WorkflowClarification | None) -> dict[str, object]:
		payload = json.loads(WorkflowPlanner.serialize_plan(plan))
		if isinstance(payload, dict):
			return payload
		return {"route": "chat"}

	def _format_validation_error(self, errors: list[dict[str, object]]) -> str:
		if not errors:
			return "workflow 输入校验失败，未执行。"
		first_error = errors[0]
		location = first_error.get("loc")
		field_path = ".".join(str(part) for part in location) if isinstance(location, (tuple, list)) else "input"
		message = str(first_error.get("msg") or "invalid workflow input")
		return f"workflow 输入校验失败，未执行：{field_path} {message}。"

	def _build_workflow_validation_failure_result(
		self,
		*,
		session_id: str,
		message: str,
		plan: WorkflowPlan,
		validation_errors: list[dict[str, object]],
		pending_clarification: dict[str, object] | None = None,
	) -> AgentRunResult:
		state = AgentState(session_id=session_id, user_message=message.strip())
		now = self._now()
		state.phase = AgentPhase.FAILED
		state.last_phase_started_at = now
		state.completed_at = now
		state.error = "Workflow input validation failed."
		state.planning_text = WorkflowPlanner.serialize_plan(plan)
		state.planner_result = self._serialize_planner_result(plan)
		state.pending_workflow_clarification = pending_clarification
		state.workflow_execution = {
			"workflow_type": plan.workflow_type,
			"input": plan.input_payload,
			"status": "not_run",
		}
		state.workflow_validation_error = {
			"workflow_type": plan.workflow_type,
			"input": plan.input_payload,
			"errors": validation_errors,
		}
		state.final_text = self._format_validation_error(validation_errors)
		state.final_chunks = [state.final_text]
		state.phase_durations_ms = {
			AgentPhase.PLANNING.value: 0.0,
			AgentPhase.FAILED.value: 0.0,
		}
		return AgentRunResult(state=state, output=state.final_text)

	def _validate_workflow_plan(self, plan: WorkflowPlan) -> list[dict[str, object]] | None:
		try:
			self._workflow_service.validate_workflow_input(plan.workflow_type, plan.input_payload)
		except ValidationError as exc:
			return exc.errors()
		return None

	async def _plan_next_action(self, session_id: str, message: str) -> WorkflowPlan | WorkflowClarification | None:
		pending = self._workflow_clarification_store.get(session_id)
		if pending is not None:
			try:
				result = await self._workflow_planner.resolve_clarification(
					clarification=pending.clarification,
					original_message=pending.original_message,
					followup_message=message,
				)
			except ValueError:
				result = None
			if isinstance(result, WorkflowPlan):
				result = WorkflowPlan(
					workflow_type=result.workflow_type,
					input_payload={**pending.clarification.input_payload, **result.input_payload},
					rationale=result.rationale,
				)
				self._workflow_clarification_store.clear(session_id)
				return result
			if isinstance(result, WorkflowClarification):
				merged_clarification = WorkflowClarification(
					workflow_type=result.workflow_type,
					missing_fields=result.missing_fields,
					message=result.message,
					input_payload={**pending.clarification.input_payload, **result.input_payload},
					rationale=result.rationale,
				)
				self._workflow_clarification_store.set(session_id, merged_clarification, pending.original_message)
				return merged_clarification
			self._workflow_clarification_store.clear(session_id)

		return await self._plan_workflow(message)

	def _build_clarification_result(
		self,
		*,
		session_id: str,
		message: str,
		clarification: WorkflowClarification,
	) -> AgentRunResult:
		state = AgentState(session_id=session_id, user_message=message.strip())
		now = self._now()
		state.phase = AgentPhase.COMPLETED
		state.last_phase_started_at = now
		state.completed_at = now
		state.planning_text = WorkflowPlanner.serialize_plan(clarification)
		state.planner_result = self._serialize_planner_result(clarification)
		state.pending_workflow_clarification = {
			"workflow_type": clarification.workflow_type,
			"missing_fields": clarification.missing_fields,
			"clarification_message": clarification.message,
			"input": clarification.input_payload,
			"rationale": clarification.rationale,
		}
		state.final_text = clarification.message
		state.final_chunks = [state.final_text]
		state.phase_durations_ms = {
			AgentPhase.PLANNING.value: 0.0,
			AgentPhase.COMPLETED.value: 0.0,
		}
		return AgentRunResult(state=state, output=state.final_text)

	async def _plan_workflow(self, message: str) -> WorkflowPlan | WorkflowClarification | None:
		try:
			return await self._workflow_planner.plan(message)
		except ValueError:
			return None

	async def run_response(self, session_id: str, message: str) -> AgentRunResult:
		pending = self._workflow_clarification_store.get(session_id)
		plan = await self._plan_next_action(session_id, message)
		if isinstance(plan, WorkflowClarification):
			original_message = pending.original_message if pending is not None else message
			self._workflow_clarification_store.set(session_id, plan, original_message)
			return self._build_clarification_result(
				session_id=session_id,
				message=message,
				clarification=plan,
			)
		if isinstance(plan, WorkflowPlan):
			self._workflow_clarification_store.clear(session_id)
			validation_errors = self._validate_workflow_plan(plan)
			if validation_errors is not None:
				return self._build_workflow_validation_failure_result(
					session_id=session_id,
					message=message,
					plan=plan,
					validation_errors=validation_errors,
					pending_clarification=pending.to_dict() if pending is not None else None,
				)
			workflow_result = await self._workflow_service.run_workflow(
				plan.workflow_type,
				session_id=session_id,
				**plan.input_payload,
			)
			return self._build_workflow_run_result(
				session_id=session_id,
				message=message,
				plan=plan,
				workflow_result=workflow_result,
				pending_clarification=pending.to_dict() if pending is not None else None,
			)
		return await self._agent.run(session_id, message)

	def _progress_event(self, phase: str, message: str, **extra: object) -> str:
		payload = {"type": "phase", "phase": phase, "message": message, **extra}
		return f"§event:{json.dumps(payload, ensure_ascii=False)}\n"

	def _artifact_event(
		self,
		*,
		artifact_key: str,
		artifact: object,
		step_name: str,
		step_status: str,
		workflow_type: str,
		duration_ms: float,
	) -> str:
		payload = {
			"type": "artifact",
			"artifact_key": artifact_key,
			"artifact": artifact,
			"step_name": step_name,
			"step_status": step_status,
			"workflow_type": workflow_type,
			"duration_ms": duration_ms,
		}
		return f"§event:{json.dumps(payload, ensure_ascii=False)}\n"

	def _get_workflow_step_names(self, workflow_type: str) -> list[str]:
		step_map = {
			"meeting": ["summary", "action_items", "memo", "save_memory", "send_teams"],
			"bug": ["analysis", "jira_comment", "post_jira_comment"],
		}
		return step_map.get(workflow_type, [])

	async def stream_response(self, session_id: str, message: str) -> AsyncIterator[str]:
		pending = self._workflow_clarification_store.get(session_id)

		yield self._progress_event("planning", "正在分析意图...")
		plan = await self._plan_next_action(session_id, message)

		if isinstance(plan, WorkflowClarification):
			yield self._progress_event("planning", f"需要补充信息: {', '.join(plan.missing_fields)}", missing=plan.missing_fields)
			original_message = pending.original_message if pending is not None else message
			self._workflow_clarification_store.set(session_id, plan, original_message)
			yield self._build_clarification_result(
				session_id=session_id,
				message=message,
				clarification=plan,
			).output
			return

		if isinstance(plan, WorkflowPlan):
			yield self._progress_event("planning", f"识别到 {plan.workflow_type} workflow", workflow_type=plan.workflow_type)
			self._workflow_clarification_store.clear(session_id)
			validation_errors = self._validate_workflow_plan(plan)
			if validation_errors is not None:
				yield self._progress_event("workflow", "输入校验失败")
				yield self._build_workflow_validation_failure_result(
					session_id=session_id,
					message=message,
					plan=plan,
					validation_errors=validation_errors,
					pending_clarification=pending.to_dict() if pending is not None else None,
				).output
				return

			yield self._progress_event("workflow", f"正在执行 {plan.workflow_type} workflow...")

			# Get step names for progress reporting
			step_names = self._get_workflow_step_names(plan.workflow_type)
			if step_names:
				yield self._progress_event("workflow", f"步骤: {' → '.join(step_names)}", steps=step_names)

			workflow_result = await self._workflow_service.run_workflow(
				plan.workflow_type,
				session_id=session_id,
				**plan.input_payload,
			)

			# Report each step result and emit artifacts
			for step in workflow_result.steps:
				status_text = {"success": "✓", "failed": "✗", "skipped": "○"}.get(step.status.value, "?")
				yield self._progress_event(
					"workflow",
					f"{status_text} {step.step_name} ({step.duration_ms:.0f}ms)",
					step_name=step.step_name,
					step_status=step.status.value,
					duration_ms=step.duration_ms,
				)
				if step.artifact_key and step.artifact is not None:
					yield self._artifact_event(
						artifact_key=step.artifact_key,
						artifact=step.artifact,
						step_name=step.step_name,
						step_status=step.status.value,
						workflow_type=plan.workflow_type,
						duration_ms=step.duration_ms,
					)

			yield self._progress_event("responding", "正在生成回答...")
			yield self._build_workflow_run_result(
				session_id=session_id,
				message=message,
				plan=plan,
				workflow_result=workflow_result,
				pending_clarification=pending.to_dict() if pending is not None else None,
			).output
			return

		yield self._progress_event("planning", "普通对话，进入 chat 流程")
		async for chunk in self._agent.stream_response(session_id, message):
			yield chunk