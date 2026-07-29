from collections import defaultdict
from datetime import datetime

class ConversationMemory:
    def __init__(self, max_messages: int = 20) -> None:
        self._max_messages = max_messages
        self._store: dict[str, list[dict[str, str]]] = defaultdict(list)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._store[session_id].append(message)
        if len(self._store[session_id]) > self._max_messages:
            self._store[session_id] = self._store[session_id][-self._max_messages:]

    def get_recent_messages(self, session_id: str, limit: int = 10) -> list[dict[str, str]]:
        return self._store.get(session_id, [])[-limit:]

    def clear_session(self, session_id: str) -> None:
        if session_id in self._store:
            del self._store[session_id]