from dataclasses import dataclass
from datetime import datetime

from app.agent.state import AgentPhase, AgentState


@dataclass(frozen=True)
class AgentHookEvent:
	state: AgentState
	timestamp: datetime
	elapsed_ms: float
	phase_elapsed_ms: float


@dataclass(frozen=True)
class AgentPhaseChangeEvent(AgentHookEvent):
	previous_phase: AgentPhase
	current_phase: AgentPhase


@dataclass(frozen=True)
class AgentChunkEvent(AgentHookEvent):
	chunk: str


@dataclass(frozen=True)
class AgentErrorEvent(AgentHookEvent):
	error: str


@dataclass(frozen=True)
class AgentCompletionEvent(AgentHookEvent):
	output: str


class AgentRuntimeHook:
	"""Lifecycle hook surface for observing AgentRuntime execution."""

	def on_phase_change(self, event: AgentPhaseChangeEvent) -> None:
		return None

	def on_chunk(self, event: AgentChunkEvent) -> None:
		return None

	def on_error(self, event: AgentErrorEvent) -> None:
		return None

	def on_complete(self, event: AgentCompletionEvent) -> None:
		return None