import logging
import httpx
from typing import List, Dict, Any, Optional
from config import settings

logger = logging.getLogger(__name__)

class KnowledgeService:
    """Service for interacting with FastGPT to retrieve augmented knowledge."""

    def __init__(self) -> None:
        self._api_key = settings.fastgpt_api_key
        self._base_url = settings.fastgpt_base_url

    async def retrieve_knowledge(self, query: str, session_id: str | None = None) -> str:
        """
        Retrieves relevant knowledge chunks from FastGPT for a given query.
        Uses the OpenAI-compatible /v1/chat/completions endpoint.
        """
        if not self._api_key:
            logger.warning("FastGPT API key not configured. Skipping knowledge retrieval.")
            return ""

        url = f"{self._base_url}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        chat_id = f"ella-agent-{session_id}" if session_id else "ella-agent-rag"

        payload = {
            "chatId": chat_id,
            "stream": False,
            "messages": [
                {"role": "user", "content": query}
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    if content:
                        return f"Relevant knowledge found:\n{content}"

                return ""

        except Exception as exc:
            logger.error(f"Error retrieving knowledge from FastGPT: {exc}")
            return ""
