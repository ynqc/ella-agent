from typing import Any

from pydantic import BaseModel, Field

from app.workflows.contracts import BugWorkflowInput, MeetingWorkflowInput


class ChatRequest(BaseModel):
	session_id: str | None = Field(default=None, min_length=1, max_length=128)
	message: str = Field(min_length=1, max_length=20000)


class WorkflowRunRequest(BaseModel):
	workflow_type: str = Field(min_length=1, max_length=64)
	session_id: str | None = Field(default=None, min_length=1, max_length=128)
	input: dict[str, Any] = Field(default_factory=dict)


class AgentStateDebugResponse(BaseModel):
	session_id: str
	user_message: str
	phase: str
	started_at: str
	last_phase_started_at: str | None
	completed_at: str | None
	phase_durations_ms: dict[str, float]
	total_duration_ms: float | None
	error: str | None
	effective_message: str | None
	memory_context: str | None
	knowledge_context: str | None
	memory_extraction_messages: list[dict[str, Any]]
	raw_memories: list[dict[str, Any]]
	extracted_memories: list[dict[str, Any]]
	tools: list[dict[str, Any]]
	tool_schemas: list[dict[str, Any]]
	planning_messages: list[dict[str, Any]]
	planning_text: str
	tool_calls: list[dict[str, Any]]
	tool_results: list[dict[str, Any]]
	tool_followup_messages: list[dict[str, Any]]
	planner_result: dict[str, Any] | None = None
	pending_workflow_clarification: dict[str, Any] | None = None
	workflow_execution: dict[str, Any] | None = None
	workflow_validation_error: dict[str, Any] | None = None
	final_chunks: list[str]
	final_text: str


class AgentRunDebugResponse(BaseModel):
	session_id: str
	output: str
	state: AgentStateDebugResponse


class WorkflowStepResponse(BaseModel):
	step_name: str
	status: str
	artifact_key: str | None
	artifact: Any | None
	error: str | None
	started_at: str
	completed_at: str
	duration_ms: float


class WorkflowRunResponse(BaseModel):
	workflow_id: str
	workflow_type: str
	session_id: str
	status: str
	steps: list[WorkflowStepResponse]
	artifacts: dict[str, Any]
	started_at: str
	completed_at: str
	error: str | None
	cache: dict[str, Any] | None = None