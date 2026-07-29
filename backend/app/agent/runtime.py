from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json
import logging

from app.agent.hooks import (
	AgentChunkEvent,
	AgentCompletionEvent,
	AgentErrorEvent,
	AgentPhaseChangeEvent,
	AgentRuntimeHook,
)
from app.agent.state import AgentPhase, AgentRunResult, AgentState
from app.llm.client import LLMClient
from app.llm.prompt_builder import EffectiveUserMessageRequest
from app.memory.memory_manager import MemoryManager
from app.services.tool_dispatcher import ToolDispatcher


class AgentRuntime:
	"""Executes the per-request chat workflow against a mutable AgentState."""

	def __init__(
		self,
		tool_dispatcher: ToolDispatcher,
		llm_client: LLMClient,
		memory_manager: MemoryManager,
		logger: logging.Logger,
		hooks: list[AgentRuntimeHook] | None = None,
	) -> None:
		self._tool_dispatcher = tool_dispatcher
		self._llm_client = llm_client
		self._memory_manager = memory_manager
		self._logger = logger
		self._hooks = hooks or []

	def _now(self) -> datetime:
		return datetime.now(UTC)

	def _elapsed_ms(self, state: AgentState, timestamp: datetime) -> float:
		return round((timestamp - state.started_at).total_seconds() * 1000, 3)

	def _phase_elapsed_ms(self, state: AgentState, timestamp: datetime) -> float:
		if state.last_phase_started_at is None:
			return 0.0
		return round((timestamp - state.last_phase_started_at).total_seconds() * 1000, 3)

	def _set_phase(self, state: AgentState, phase: AgentPhase) -> AgentState:
		timestamp = self._now()
		previous_phase = state.phase
		if state.last_phase_started_at is not None:
			state.phase_durations_ms[previous_phase.value] = round(
				state.phase_durations_ms.get(previous_phase.value, 0.0)
				+ (timestamp - state.last_phase_started_at).total_seconds() * 1000,
				3,
			)
		state.phase = phase
		state.last_phase_started_at = timestamp
		for hook in self._hooks:
			hook.on_phase_change(
				AgentPhaseChangeEvent(
					state=state,
					timestamp=timestamp,
					elapsed_ms=self._elapsed_ms(state, timestamp),
					phase_elapsed_ms=0.0,
					previous_phase=previous_phase,
					current_phase=phase,
				)
			)
		return state

	def _notify_chunk(self, state: AgentState, chunk: str) -> str:
		timestamp = self._now()
		state.final_chunks.append(chunk)
		for hook in self._hooks:
			hook.on_chunk(
				AgentChunkEvent(
					state=state,
					timestamp=timestamp,
					elapsed_ms=self._elapsed_ms(state, timestamp),
					phase_elapsed_ms=self._phase_elapsed_ms(state, timestamp),
					chunk=chunk,
				)
			)
		return chunk

	def _notify_error(self, state: AgentState, error: str) -> None:
		timestamp = self._now()
		state.error = error
		for hook in self._hooks:
			hook.on_error(
				AgentErrorEvent(
					state=state,
					timestamp=timestamp,
					elapsed_ms=self._elapsed_ms(state, timestamp),
					phase_elapsed_ms=self._phase_elapsed_ms(state, timestamp),
					error=error,
				)
			)

	def _notify_complete(self, state: AgentState) -> None:
		timestamp = self._now()
		phase_elapsed_ms = self._phase_elapsed_ms(state, timestamp)
		state.completed_at = timestamp
		if state.last_phase_started_at is not None:
			state.phase_durations_ms[state.phase.value] = round(
				state.phase_durations_ms.get(state.phase.value, 0.0)
				+ (timestamp - state.last_phase_started_at).total_seconds() * 1000,
				3,
			)
			state.last_phase_started_at = timestamp
		for hook in self._hooks:
			hook.on_complete(
				AgentCompletionEvent(
					state=state,
					timestamp=timestamp,
					elapsed_ms=self._elapsed_ms(state, timestamp),
					phase_elapsed_ms=phase_elapsed_ms,
					output=state.final_text,
				)
			)

	async def _plan_response(self, state: AgentState) -> AgentState:
		tools = self._tool_dispatcher.list_tools()
		llm = self._llm_client._build_llm()
		tool_schemas = self._llm_client.build_tool_schemas(tools)
		planning_messages = self._llm_client.build_planning_messages(
			message=state.effective_message or state.user_message,
			tools=tools,
		)
		llm_with_tools = llm.bind_tools(tool_schemas)
		planning_response = await llm_with_tools.ainvoke(planning_messages)
		state.tools = tools
		state.tool_schemas = tool_schemas
		state.planning_messages = planning_messages
		state.llm_with_tools = llm_with_tools
		state.planning_response = planning_response
		state.planning_text = self._llm_client.response_text(planning_response)
		state.tool_calls = self._llm_client.extract_tool_calls(planning_response)
		return state

	async def _capture_user_memory(self, state: AgentState) -> AgentState:
		state.memory_extraction_messages = self._llm_client.build_memory_extraction_messages(state.user_message)
		try:
			state.raw_memories = await self._llm_client.extract_memories(state.user_message)
		except Exception as exc:
			state.error = str(exc)
			self._logger.warning("memory extraction failed: %s", exc)
			return state

		if not state.raw_memories:
			return state

		extracted_memories = self._memory_manager.store_extracted_memories(state.session_id, state.raw_memories)
		state.extracted_memories = [memory.__dict__ for memory in extracted_memories]
		if extracted_memories:
			self._logger.info(
				"captured user memories: %s",
				json.dumps(state.extracted_memories, ensure_ascii=False),
			)
		return state

	def _build_effective_message(self, state: AgentState) -> AgentState:
		state.memory_context = self._memory_manager.build_memory_context(state.session_id, state.user_message)
		state.effective_message = self._llm_client.prompt_builder.build_effective_user_message(
			EffectiveUserMessageRequest(message=state.user_message, memory_context=state.memory_context or "")
		)
		return state

	def _run_tool_calls(self, state: AgentState) -> AgentState:
		state.tool_results = [
			self._tool_dispatcher.dispatch(tool_call["name"], tool_call["args"])
			for tool_call in state.tool_calls
		]
		return state

	async def run(self, state: AgentState) -> AgentRunResult:
		parts: list[str] = []
		async for chunk in self.stream(state):
			parts.append(chunk)
		output = "".join(parts)
		if output and not state.final_text:
			state.final_text = output
		return AgentRunResult(state=state, output=output)

	async def stream(self, state: AgentState) -> AsyncIterator[str]:
		self._set_phase(state, AgentPhase.RECEIVED)
		self._logger.info("chat request received")
		self._memory_manager.add_user_message(state.session_id, state.user_message)

		self._set_phase(state, AgentPhase.MEMORY_CAPTURE)
		state = await self._capture_user_memory(state)

		self._set_phase(state, AgentPhase.PROMPT_BUILD)
		state = self._build_effective_message(state)

		self._set_phase(state, AgentPhase.PLANNING)
		try:
			state = await self._plan_response(state)
		except ValueError as exc:
			self._set_phase(state, AgentPhase.FAILED)
			self._notify_error(state, str(exc))
			self._logger.warning("tool call parsing failed: %s", exc)
			error_payload = json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2)
			yield self._notify_chunk(state, error_payload)
			self._notify_complete(state)
			return

		if not state.tool_calls:
			self._set_phase(state, AgentPhase.RESPONDING)
			self._logger.info("llm answered without tool call")
			text = self._llm_client.response_text(state.planning_response)
			if text:
				state.final_text = text
				self._memory_manager.add_assistant_message(state.session_id, text)
				yield self._notify_chunk(state, text)
			self._set_phase(state, AgentPhase.COMPLETED)
			self._notify_complete(state)
			return

		self._logger.info(
			"llm selected tool calls: %s",
			json.dumps(state.tool_calls, ensure_ascii=False),
		)

		self._set_phase(state, AgentPhase.TOOL_EXECUTION)
		state = self._run_tool_calls(state)
		self._logger.info(
			"tool execution results: %s",
			json.dumps(state.tool_results, ensure_ascii=False),
		)

		state.tool_followup_messages = self._llm_client.build_tool_followup_messages(
			message=state.effective_message or state.user_message,
			tools=state.tools,
			planning_response=state.planning_response,
			tool_calls=state.tool_calls,
			tool_results=state.tool_results,
		)
		self._set_phase(state, AgentPhase.RESPONDING)
		async for text in self._llm_client.stream_final_answer(
			state.llm_with_tools,
			state.effective_message or state.user_message,
			state.tools,
			state.planning_response,
			state.tool_calls,
			state.tool_results,
			followup_messages=state.tool_followup_messages,
		):
			yield self._notify_chunk(state, text)

		state.final_text = "".join(state.final_chunks)
		if state.final_text:
			self._memory_manager.add_assistant_message(state.session_id, state.final_text)
		self._set_phase(state, AgentPhase.COMPLETED)
		self._notify_complete(state)