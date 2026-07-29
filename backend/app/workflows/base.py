from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class WorkflowStepStatus(StrEnum):
	SUCCESS = "success"
	FAILED = "failed"
	SKIPPED = "skipped"


class WorkflowRunStatus(StrEnum):
	COMPLETED = "completed"
	FAILED = "failed"


@dataclass
class WorkflowContext:
	workflow_id: str
	workflow_type: str
	session_id: str
	input_payload: dict[str, Any]
	artifacts: dict[str, Any] = field(default_factory=dict)
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowStepOutcome:
	status: WorkflowStepStatus
	artifact_key: str | None = None
	artifact: Any | None = None
	error: str | None = None


@dataclass(frozen=True)
class WorkflowStepResult:
	step_name: str
	status: WorkflowStepStatus
	artifact_key: str | None
	artifact: Any | None
	error: str | None
	started_at: datetime
	completed_at: datetime
	duration_ms: float

	def to_dict(self) -> dict[str, Any]:
		return {
			"step_name": self.step_name,
			"status": self.status.value,
			"artifact_key": self.artifact_key,
			"artifact": self.artifact,
			"error": self.error,
			"started_at": self.started_at.isoformat(),
			"completed_at": self.completed_at.isoformat(),
			"duration_ms": self.duration_ms,
		}

	@classmethod
	def from_dict(cls, payload: dict[str, Any]) -> "WorkflowStepResult":
		return cls(
			step_name=str(payload["step_name"]),
			status=WorkflowStepStatus(str(payload["status"])),
			artifact_key=payload.get("artifact_key"),
			artifact=payload.get("artifact"),
			error=payload.get("error"),
			started_at=datetime.fromisoformat(str(payload["started_at"])),
			completed_at=datetime.fromisoformat(str(payload["completed_at"])),
			duration_ms=float(payload["duration_ms"]),
		)


class WorkflowStep(Protocol):
	name: str

	async def run(self, context: WorkflowContext) -> WorkflowStepOutcome:
		...


@dataclass(frozen=True)
class WorkflowRunResult:
	workflow_id: str
	workflow_type: str
	session_id: str
	status: WorkflowRunStatus
	steps: list[WorkflowStepResult]
	artifacts: dict[str, Any]
	started_at: datetime
	completed_at: datetime
	error: str | None = None
	cache: dict[str, Any] | None = None

	def to_dict(self) -> dict[str, Any]:
		return {
			"workflow_id": self.workflow_id,
			"workflow_type": self.workflow_type,
			"session_id": self.session_id,
			"status": self.status.value,
			"steps": [step.to_dict() for step in self.steps],
			"artifacts": self.artifacts,
			"started_at": self.started_at.isoformat(),
			"completed_at": self.completed_at.isoformat(),
			"error": self.error,
			"cache": self.cache,
		}

	@classmethod
	def from_dict(cls, payload: dict[str, Any]) -> "WorkflowRunResult":
		return cls(
			workflow_id=str(payload["workflow_id"]),
			workflow_type=str(payload["workflow_type"]),
			session_id=str(payload["session_id"]),
			status=WorkflowRunStatus(str(payload["status"])),
			steps=[WorkflowStepResult.from_dict(step) for step in payload.get("steps", [])],
			artifacts=dict(payload.get("artifacts", {})),
			started_at=datetime.fromisoformat(str(payload["started_at"])),
			completed_at=datetime.fromisoformat(str(payload["completed_at"])),
			error=payload.get("error"),
			cache=payload.get("cache"),
		)

	def with_cache(self, cache: dict[str, Any]) -> "WorkflowRunResult":
		return replace(self, cache=cache)

	def with_session_id(self, session_id: str) -> "WorkflowRunResult":
		return replace(self, session_id=session_id)

	def with_steps(self, steps: list[WorkflowStepResult]) -> "WorkflowRunResult":
		return replace(self, steps=steps)

	def with_artifacts(self, artifacts: dict[str, Any]) -> "WorkflowRunResult":
		return replace(self, artifacts=artifacts)


class WorkflowRunner:
	def _now(self) -> datetime:
		return datetime.now(UTC)

	async def run(
		self,
		workflow_type: str,
		context: WorkflowContext,
		steps: Sequence[WorkflowStep],
	) -> WorkflowRunResult:
		started_at = self._now()
		step_results: list[WorkflowStepResult] = []

		for step in steps:
			step_started_at = self._now()
			try:
				outcome = await step.run(context)
			except Exception as exc:
				outcome = WorkflowStepOutcome(
					status=WorkflowStepStatus.FAILED,
					error=str(exc),
				)

			step_completed_at = self._now()
			result = WorkflowStepResult(
				step_name=step.name,
				status=outcome.status,
				artifact_key=outcome.artifact_key,
				artifact=outcome.artifact,
				error=outcome.error,
				started_at=step_started_at,
				completed_at=step_completed_at,
				duration_ms=round((step_completed_at - step_started_at).total_seconds() * 1000, 3),
			)
			step_results.append(result)

			if outcome.artifact_key is not None:
				context.artifacts[outcome.artifact_key] = outcome.artifact

			if outcome.status == WorkflowStepStatus.FAILED:
				completed_at = self._now()
				return WorkflowRunResult(
					workflow_id=context.workflow_id,
					workflow_type=workflow_type,
					session_id=context.session_id,
					status=WorkflowRunStatus.FAILED,
					steps=step_results,
					artifacts=dict(context.artifacts),
					started_at=started_at,
					completed_at=completed_at,
					error=outcome.error,
				)

		completed_at = self._now()
		return WorkflowRunResult(
			workflow_id=context.workflow_id,
			workflow_type=workflow_type,
			session_id=context.session_id,
			status=WorkflowRunStatus.COMPLETED,
			steps=step_results,
			artifacts=dict(context.artifacts),
			started_at=started_at,
			completed_at=completed_at,
		)