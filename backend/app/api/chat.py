from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from app.api.dependencies import get_chat_service
from app.api.schemas import AgentRunDebugResponse, ChatRequest
from config import settings
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api", tags=["chat"])


async def text_stream(service: ChatService, session_id: str, message: str) -> AsyncIterator[bytes]:
	async for chunk in service.stream_response(session_id, message):
		yield chunk.encode("utf-8")

@router.post("/chat")
async def create_chat_completion(
	payload: ChatRequest,
	service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
	session_id = payload.session_id or f"session-{uuid4().hex}"
	return StreamingResponse(
		text_stream(service, session_id, payload.message),
		media_type="text/plain; charset=utf-8",
		headers={"X-Session-Id": session_id},
	)


@router.post("/chat/debug", response_model=AgentRunDebugResponse)
async def create_chat_completion_debug(
	payload: ChatRequest,
	service: Annotated[ChatService, Depends(get_chat_service)],
) -> AgentRunDebugResponse:
	if not settings.agent_runtime_debug_enabled:
		raise HTTPException(status_code=404, detail="Not found")

	session_id = payload.session_id or f"session-{uuid4().hex}"
	result = await service.run_response(session_id, payload.message)
	debug_payload = result.to_debug_dict()
	debug_payload["session_id"] = session_id
	return AgentRunDebugResponse.model_validate(debug_payload)