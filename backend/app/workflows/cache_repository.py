from sqlalchemy import select
from sqlalchemy.orm import Session

from app.workflows.cache_models import WorkflowArtifactCache


class WorkflowArtifactCacheRepository:
	def __init__(self, session: Session) -> None:
		self._session = session

	def get_by_scope(
		self,
		workflow_type: str,
		input_hash: str,
		cache_scope: str,
	) -> WorkflowArtifactCache | None:
		stmt = (
			select(WorkflowArtifactCache)
			.where(WorkflowArtifactCache.workflow_type == workflow_type)
			.where(WorkflowArtifactCache.input_hash == input_hash)
			.where(WorkflowArtifactCache.cache_scope == cache_scope)
			.order_by(WorkflowArtifactCache.updated_at.desc())
			.limit(1)
		)
		result = self._session.execute(stmt)
		return result.scalars().first()

	def save_or_update(
		self,
		*,
		workflow_type: str,
		session_id: str | None,
		input_hash: str,
		normalized_input: str,
		cache_scope: str,
		result_json: str,
	) -> WorkflowArtifactCache:
		record = self.get_by_scope(workflow_type, input_hash, cache_scope)
		if record is None:
			record = WorkflowArtifactCache(
				workflow_type=workflow_type,
				session_id=session_id,
				input_hash=input_hash,
				normalized_input=normalized_input,
				cache_scope=cache_scope,
				result_json=result_json,
			)
		else:
			record.session_id = session_id
			record.normalized_input = normalized_input
			record.result_json = result_json

		self._session.add(record)
		self._session.commit()
		self._session.refresh(record)
		return record