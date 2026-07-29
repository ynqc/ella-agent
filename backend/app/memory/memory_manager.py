from dataclasses import dataclass

from app.memory.conversation_memory import ConversationMemory
from app.memory.database import SessionLocal
from app.memory.policy import MemoryPolicy
from app.memory.ranker import MemoryRanker, build_memory_conflict_key
from app.memory.repository import MemoryRepository


@dataclass(frozen=True)
class ExtractedMemory:
    memory_type: str
    content: str
    keywords: tuple[str, ...] = ()


class MemoryManager:
    def __init__(
        self,
        conversation_memory: ConversationMemory | None = None,
        memory_ranker: MemoryRanker | None = None,
        memory_policy: MemoryPolicy | None = None,
    ) -> None:
        self._conversation_memory = conversation_memory or ConversationMemory()
        self._memory_policy = memory_policy or MemoryPolicy()
        self._memory_ranker = memory_ranker or MemoryRanker(self._memory_policy)

    def _save_conversation_message(self, session_id: str, role: str, content: str) -> None:
        session = SessionLocal()
        try:
            MemoryRepository(session).save_conversation_message(session_id, role, content)
        finally:
            session.close()

    def _save_memory(
        self,
        session_id: str | None,
        memory_type: str,
        content: str,
        keywords: str | None = None,
    ) -> None:
        session = SessionLocal()
        try:
            MemoryRepository(session).save_memory(session_id, memory_type, content, keywords)
        finally:
            session.close()

    def _update_memory(
        self,
        memory: object,
        *,
        content: str,
        keywords: str | None,
    ) -> None:
        session = SessionLocal()
        try:
            repository = MemoryRepository(session)
            persisted_memory = session.get(type(memory), memory.id)
            if persisted_memory is None:
                repository.save_memory(memory.session_id, memory.memory_type, content, keywords)
                return
            repository.update_memory(
                persisted_memory,
                content=content,
                keywords=keywords,
            )
        finally:
            session.close()

    def _find_conflicting_memories(
        self,
        session_id: str | None,
        memory_type: str,
        content: str,
    ) -> list[object]:
        session = SessionLocal()
        try:
            repository = MemoryRepository(session)
            memories = repository.list_memories_by_type(session_id, memory_type)
        finally:
            session.close()

        conflict_key = self._memory_policy.conflict_key(memory_type, content)
        return [
            memory
            for memory in memories
            if self._memory_policy.conflict_key(memory.memory_type, memory.content) == conflict_key
        ]

    def _delete_memories(self, memories: list[object]) -> None:
        session = SessionLocal()
        try:
            MemoryRepository(session).delete_memories(memories)
        finally:
            session.close()
    
    def add_user_message(self, session_id: str, content: str) -> None:
        self._conversation_memory.add_message(session_id, "user", content)
        self._save_conversation_message(session_id, "user", content)

    def add_assistant_message(self, session_id: str, content: str) -> None:
        self._conversation_memory.add_message(session_id, "assistant", content)
        self._save_conversation_message(session_id, "assistant", content)

    def remember(
        self,
        session_id: str | None,
        memory_type: str,
        content: str,
        keywords: str | None = None,
    ) -> None:
        self._save_memory(session_id, memory_type, content, keywords)

    def store_extracted_memories(self, session_id: str, raw_memories: list[dict[str, object]]) -> list[ExtractedMemory]:
        extracted_memories = self._deduplicate_extracted_memories(
            self._normalize_extracted_memories(raw_memories)
        )
        for memory in extracted_memories:
            serialized_keywords = self._serialize_keywords(memory.keywords)
            conflicting_memories = self._find_conflicting_memories(
                session_id,
                memory.memory_type,
                memory.content,
            )
            has_exact_duplicate = any(
                existing_memory.content == memory.content
                and (existing_memory.keywords or "") == (serialized_keywords or "")
                for existing_memory in conflicting_memories
            )
            if has_exact_duplicate:
                continue

            if conflicting_memories:
                primary_memory = conflicting_memories[0]
                extra_conflicts = conflicting_memories[1:]
                self._update_memory(
                    primary_memory,
                    content=memory.content,
                    keywords=serialized_keywords,
                )
                if extra_conflicts:
                    self._delete_memories(extra_conflicts)
                continue

            self.remember(
                session_id,
                memory.memory_type,
                memory.content,
                serialized_keywords,
            )
        return extracted_memories

    def _deduplicate_extracted_memories(self, memories: list[ExtractedMemory]) -> list[ExtractedMemory]:
        selected: dict[tuple[str, str], ExtractedMemory] = {}

        for memory in memories:
            dedupe_key = (
                memory.memory_type,
                self._memory_policy.conflict_key(memory.memory_type, memory.content),
            )
            selected[dedupe_key] = memory

        return list(selected.values())

    def _normalize_extracted_memories(self, raw_memories: list[dict[str, object]]) -> list[ExtractedMemory]:
        normalized_memories: list[ExtractedMemory] = []

        for raw_memory in raw_memories:
            if not isinstance(raw_memory, dict):
                continue

            memory_type = raw_memory.get("memory_type")
            content = raw_memory.get("content")
            raw_keywords = raw_memory.get("keywords", [])

            if not isinstance(memory_type, str) or not memory_type.strip():
                continue
            if not isinstance(content, str) or not content.strip():
                continue

            keywords = self._normalize_keywords(raw_keywords)
            normalized_memories.append(
                ExtractedMemory(
                    memory_type=memory_type.strip(),
                    content=content.strip(),
                    keywords=keywords,
                )
            )

        return normalized_memories

    def _normalize_keywords(self, raw_keywords: object) -> tuple[str, ...]:
        if isinstance(raw_keywords, str):
            items = raw_keywords.split(",")
        elif isinstance(raw_keywords, list):
            items = [item for item in raw_keywords if isinstance(item, str)]
        else:
            items = []

        normalized_items: list[str] = []
        for item in items:
            keyword = item.strip()
            if keyword and keyword not in normalized_items:
                normalized_items.append(keyword)

        return tuple(normalized_items)

    def _serialize_keywords(self, keywords: tuple[str, ...]) -> str | None:
        if not keywords:
            return None
        return ",".join(keywords)

    def get_recent_conversation(self, session_id: str, limit: int = 10) -> list[dict[str, str]]:
        return self._conversation_memory.get_recent_messages(session_id, limit)

    def search_relevant_memories(self, query: str, session_id: str, limit: int = 5) -> list[dict[str, str]]:
        session = SessionLocal()
        try:
            memories = MemoryRepository(session).search_memories(query, session_id, max(limit * 3, limit))
        finally:
            session.close()

        ranked_memories = self._memory_ranker.rank(
            query,
            memories,
            session_id=session_id,
            limit=limit,
        )
        return [
            {
                "memory_type": memory.memory_type,
                "content": memory.content,
                "keywords": memory.keywords,
                "created_at": memory.created_at.isoformat(),
            }
            for memory in ranked_memories
        ]

    def build_memory_context(self, session_id: str, user_message: str) -> str:
        recent_messages = self.get_recent_conversation(session_id, limit=10)
        relevant_memories = self.search_relevant_memories(
            user_message,
            session_id,
            limit=self._memory_policy.context_memory_limit,
        )

        context_parts = []

        if recent_messages:
            context_parts.append("Recent conversation messages:")
            for msg in recent_messages:
                context_parts.append(f"{msg['role'].capitalize()}: {msg['content']}")

        if relevant_memories:
            context_parts.append("Relevant memories:")
            for mem in self._compress_context_memories(relevant_memories):
                context_parts.append(
                    f"Memory Type: {mem['memory_type']}, Content: {mem['content']}, Keywords: {mem['keywords']}, Created At: {mem['created_at']}"
                )

        return "\n".join(context_parts)

    def _compress_context_memories(self, memories: list[dict[str, str]]) -> list[dict[str, str]]:
        selected: dict[tuple[str, str], dict[str, str]] = {}

        for memory in memories:
            conflict_key = self._memory_policy.conflict_key(memory["memory_type"], memory["content"])
            dedupe_key = (memory["memory_type"], conflict_key)
            selected.setdefault(dedupe_key, memory)

        return list(selected.values())