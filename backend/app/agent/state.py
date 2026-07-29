from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AgentPhase(StrEnum):
	INITIALIZED = "initialized"
	RECEIVED = "received"
	MEMORY_CAPTURE = "memory_capture"
	PROMPT_BUILD = "prompt_build"
	PLANNING = "planning"
	TOOL_EXECUTION = "tool_execution"
	RESPONDING = "responding"
	FAILED = "failed"
	COMPLETED = "completed"


@dataclass
class AgentState:
	session_id: str
	user_message: str
	phase: AgentPhase = AgentPhase.INITIALIZED
	started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
	last_phase_started_at: datetime | None = None
	completed_at: datetime | None = None
	phase_durations_ms: dict[str, float] = field(default_factory=dict)
	error: str | None = None
	effective_message: str | None = None
	memory_context: str | None = None
	memory_extraction_messages: list[dict[str, Any]] = field(default_factory=list)
	raw_memories: list[dict[str, object]] = field(default_factory=list)
	extracted_memories: list[dict[str, object]] = field(default_factory=list)
	tools: list[dict[str, Any]] = field(default_factory=list)
	tool_schemas: list[dict[str, Any]] = field(default_factory=list)
	planning_messages: list[dict[str, Any]] = field(default_factory=list)
	planning_text: str = ""
	llm_with_tools: Any | None = None
	planning_response: Any | None = None
	tool_calls: list[dict[str, Any]] = field(default_factory=list)
	tool_results: list[dict[str, Any]] = field(default_factory=list)
	tool_followup_messages: list[dict[str, Any]] = field(default_factory=list)
	planner_result: dict[str, Any] | None = None
	pending_workflow_clarification: dict[str, Any] | None = None
	workflow_execution: dict[str, Any] | None = None
	workflow_validation_error: dict[str, Any] | None = None
	final_chunks: list[str] = field(default_factory=list)
	final_text: str = ""

	def to_debug_dict(self) -> dict[str, Any]:
		total_duration_ms = None
		if self.completed_at is not None:
			total_duration_ms = round((self.completed_at - self.started_at).total_seconds() * 1000, 3)
		return {
			"session_id": self.session_id,
			"user_message": self.user_message,
			"phase": self.phase.value,
			"started_at": self.started_at.isoformat(),
			"last_phase_started_at": self.last_phase_started_at.isoformat() if self.last_phase_started_at else None,
			"completed_at": self.completed_at.isoformat() if self.completed_at else None,
			"phase_durations_ms": self.phase_durations_ms,
			"total_duration_ms": total_duration_ms,
			"error": self.error,
			"effective_message": self.effective_message,
			"memory_context": self.memory_context,
			"memory_extraction_messages": self.memory_extraction_messages,
			"raw_memories": self.raw_memories,
			"extracted_memories": self.extracted_memories,
			"tools": self.tools,
			"tool_schemas": self.tool_schemas,
			"planning_messages": self.planning_messages,
			"planning_text": self.planning_text,
			"tool_calls": self.tool_calls,
			"tool_results": self.tool_results,
			"tool_followup_messages": self.tool_followup_messages,
			"planner_result": self.planner_result,
			"pending_workflow_clarification": self.pending_workflow_clarification,
			"workflow_execution": self.workflow_execution,
			"workflow_validation_error": self.workflow_validation_error,
			"final_chunks": self.final_chunks,
			"final_text": self.final_text,
		}


@dataclass
class AgentRunResult:
	state: AgentState
	output: str

	def to_debug_dict(self) -> dict[str, Any]:
		return {
			"output": self.output,
			"state": self.state.to_debug_dict(),
		}