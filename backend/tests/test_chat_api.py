import unittest
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import router
from app.api.dependencies import get_chat_service


class StubChatService:
	def __init__(self) -> None:
		self.calls: list[tuple[str, str]] = []

	async def stream_response(self, session_id: str, message: str) -> AsyncIterator[str]:
		self.calls.append((session_id, message))
		yield "streamed response"


class ChatApiTests(unittest.TestCase):
	def setUp(self) -> None:
		self.service = StubChatService()
		app = FastAPI()
		app.include_router(router)
		app.dependency_overrides[get_chat_service] = lambda: self.service
		self.client = TestClient(app)

	def test_chat_endpoint_accepts_large_message_and_streams_response(self) -> None:
		message = "A" * 10000

		response = self.client.post(
			"/api/chat",
			json={
				"session_id": "session-large",
				"message": message,
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.text, "streamed response")
		self.assertEqual(response.headers.get("content-type"), "text/plain; charset=utf-8")
		self.assertEqual(self.service.calls, [("session-large", message)])