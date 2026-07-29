from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.database import Base


class WorkflowArtifactCache(Base):
	__tablename__ = "workflow_artifact_caches"
	__table_args__ = (
		UniqueConstraint("workflow_type", "input_hash", "cache_scope", name="uq_workflow_artifact_cache_scope"),
	)

	id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
	workflow_type: Mapped[str] = mapped_column(String(32), index=True)
	session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
	input_hash: Mapped[str] = mapped_column(String(64), index=True)
	normalized_input: Mapped[str] = mapped_column(Text)
	cache_scope: Mapped[str] = mapped_column(Text)
	result_json: Mapped[str] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		default=lambda: datetime.now(UTC),
		onupdate=lambda: datetime.now(UTC),
	)