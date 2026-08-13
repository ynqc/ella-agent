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
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"FastGPT request: URL={url}, chatId={chat_id}")
                response = await client.post(url, json=payload, headers=headers)
                logger.info(f"FastGPT response: status={response.status_code}, body={response.text[:500]}")
                response.raise_for_status()
                data = response.json()

                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    if content:
                        return f"Relevant knowledge found:\n{content}"

                return ""

        except httpx.HTTPStatusError as exc:
            logger.error(f"FastGPT HTTP error: status={exc.response.status_code}, body={exc.response.text[:500]}")
            return ""
        except Exception as exc:
            logger.error(f"FastGPT unexpected error: {type(exc).__name__}: {exc}")
            return ""
