from dataclasses import dataclass
from datetime import UTC, datetime

from config import settings
from app.memory.policy import MemoryPolicy

@dataclass(frozen=True)
class RankedMemory:
    memory_type: str
    content: str
    keywords: str | None
    created_at: datetime
    score: float

def build_memory_conflict_key(memory_type: str, content: str) -> str:
    return MemoryPolicy().conflict_key(memory_type, content)


class MemoryRanker:
    def __init__(self, policy: MemoryPolicy | None = None) -> None:
        self._policy = policy or MemoryPolicy(context_memory_limit=settings.memory_context_limit)

    def rank(
        self,
        query: str,
        memories: list[object],
        *,
        session_id: str | None = None,
        limit: int = 5,
    ) -> list[RankedMemory]:
        ranked_memories = [
            RankedMemory(
                memory_type=memory.memory_type,
                content=memory.content,
                keywords=memory.keywords,
                created_at=memory.created_at,
                score=self._score_memory(query, memory, session_id=session_id),
            )
            for memory in memories
        ]
        ranked_memories = self._deduplicate_conflicts(ranked_memories)
        ranked_memories.sort(
            key=lambda memory: (memory.score, memory.created_at),
            reverse=True,
        )
        return ranked_memories[:limit]

    def _score_memory(self, query: str, memory: object, *, session_id: str | None) -> float:
        normalized_query_terms = self._tokenize(query)
        normalized_content_terms = self._tokenize(memory.content)
        normalized_keyword_terms = self._tokenize(memory.keywords or "")

        keyword_hits = sum(term in normalized_keyword_terms for term in normalized_query_terms)
        content_hits = sum(term in normalized_content_terms for term in normalized_query_terms)

        type_weight = self._type_weight(memory.memory_type)
        session_weight = (
            settings.memory_ranker_session_bonus
            if session_id and getattr(memory, "session_id", None) == session_id
            else 0.0
        )
        freshness_weight = self._freshness_weight(memory.created_at)

        return (
            type_weight
            + (keyword_hits * settings.memory_ranker_keyword_hit_weight)
            + (content_hits * settings.memory_ranker_content_hit_weight)
            + session_weight
            + freshness_weight
        )

    def _type_weight(self, memory_type: str) -> float:
        return self._policy.type_weight(memory_type)

    def _deduplicate_conflicts(self, memories: list[RankedMemory]) -> list[RankedMemory]:
        selected: dict[tuple[str, str], RankedMemory] = {}

        for memory in memories:
            dedupe_key = (memory.memory_type, self._conflict_key(memory))
            existing = selected.get(dedupe_key)
            if existing is None:
                selected[dedupe_key] = memory
                continue

            if (memory.created_at, memory.score) > (existing.created_at, existing.score):
                selected[dedupe_key] = memory

        return list(selected.values())

    def _conflict_key(self, memory: RankedMemory) -> str:
        return self._policy.conflict_key(memory.memory_type, memory.content)

    def _tokenize(self, text: str) -> set[str]:
        normalized = text.lower().replace(",", " ").replace("，", " ")
        tokens = {token.strip() for token in normalized.split() if token.strip()}

        if not tokens and normalized.strip():
            tokens.add(normalized.strip())

        return tokens

    def _freshness_weight(self, created_at: datetime) -> float:
        normalized_created_at = created_at
        if normalized_created_at.tzinfo is None:
            normalized_created_at = normalized_created_at.replace(tzinfo=UTC)
        age_days = max((datetime.now(UTC) - normalized_created_at).days, 0)
        if age_days <= 1:
            return settings.memory_ranker_recent_day_bonus
        if age_days <= 7:
            return settings.memory_ranker_recent_week_bonus
        if age_days <= 30:
            return settings.memory_ranker_recent_month_bonus
        return 0.0