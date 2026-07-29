from functools import lru_cache

from app.services.chat_service import ChatService
from app.services.workflow_service import WorkflowService


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
	return ChatService(workflow_service=get_workflow_service())


@lru_cache(maxsize=1)
def get_workflow_service() -> WorkflowService:
	return WorkflowService()