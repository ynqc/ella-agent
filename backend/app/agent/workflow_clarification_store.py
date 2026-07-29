from dataclasses import dataclass

from app.agent.workflow_planner import WorkflowClarification


@dataclass(frozen=True)
class PendingWorkflowClarification:
	session_id: str
	clarification: WorkflowClarification
	original_message: str

	def to_dict(self) -> dict[str, object]:
		return {
			"workflow_type": self.clarification.workflow_type,
			"missing_fields": self.clarification.missing_fields,
			"clarification_message": self.clarification.message,
			"input": self.clarification.input_payload,
			"original_message": self.original_message,
			"rationale": self.clarification.rationale,
		}


class WorkflowClarificationStore:
	def __init__(self) -> None:
		self._pending: dict[str, PendingWorkflowClarification] = {}

	def set(self, session_id: str, clarification: WorkflowClarification, original_message: str) -> None:
		self._pending[session_id] = PendingWorkflowClarification(
			session_id=session_id,
			clarification=clarification,
			original_message=original_message,
		)

	def get(self, session_id: str) -> PendingWorkflowClarification | None:
		return self._pending.get(session_id)

	def clear(self, session_id: str) -> None:
		self._pending.pop(session_id, None)