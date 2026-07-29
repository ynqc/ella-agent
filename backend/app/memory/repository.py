from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.memory.models import ConversationMessage, Memory


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_conversation_message(self, session_id: str, role: str, content: str) -> ConversationMessage:
        message = ConversationMessage(
            session_id=session_id,
            role=role,
            content=content,
        )
        self._session.add(message)
        self._session.commit()
        self._session.refresh(message)
        return message
    
    def list_recent_conversation_messages(self, session_id: str, limit: int = 10) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        result = self._session.execute(stmt)
        return list(reversed(result.scalars().all()))
    
    def save_memory(
        self,
        session_id: str | None,
        memory_type: str,
        content: str,
        keywords: str | None = None,
    ) -> Memory:
        memory = Memory(
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            keywords=keywords,
        )
        self._session.add(memory)
        self._session.commit()
        self._session.refresh(memory)
        return memory

    def update_memory(
        self,
        memory: Memory,
        *,
        content: str,
        keywords: str | None,
    ) -> Memory:
        memory.content = content
        memory.keywords = keywords
        self._session.add(memory)
        self._session.commit()
        self._session.refresh(memory)
        return memory

    def list_memories_by_type(
        self,
        session_id: str | None,
        memory_type: str,
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.memory_type == memory_type)
        if session_id is None:
            stmt = stmt.where(Memory.session_id.is_(None))
        else:
            stmt = stmt.where(Memory.session_id == session_id)
        stmt = stmt.order_by(Memory.updated_at.desc())
        result = self._session.execute(stmt)
        return result.scalars().all()

    def delete_memories(self, memories: list[Memory]) -> None:
        if not memories:
            return

        for memory in memories:
            self._session.delete(memory)
        self._session.commit()
    
    def search_memories(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 5,
    ) -> list[Memory]:
        stmt = select(Memory).where(
            or_(
                Memory.content.ilike(f"%{query}%"),
                Memory.keywords.ilike(f"%{query}%"),
            )
        )
        if session_id:
            stmt = stmt.where(
                or_(Memory.session_id == session_id, Memory.session_id.is_(None))
            )
        stmt = stmt.order_by(Memory.updated_at.desc()).limit(limit)
        result = self._session.execute(stmt)
        return result.scalars().all()