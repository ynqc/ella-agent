from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.chat_service import ChatService
from app.services.tool_dispatcher import ToolDispatcher
from app.services.workflow_service import WorkflowService

if TYPE_CHECKING:
	from app.mcp.manager import MCPManager

_mcp_manager: MCPManager | None = None
_chat_service: ChatService | None = None
_workflow_service: WorkflowService | None = None


def init_services(mcp_manager: MCPManager | None = None) -> None:
	global _mcp_manager, _chat_service, _workflow_service
	_mcp_manager = mcp_manager
	_chat_service = None
	_workflow_service = None


def get_tool_dispatcher() -> ToolDispatcher:
	return ToolDispatcher(mcp_manager=_mcp_manager)


def get_workflow_service() -> WorkflowService:
	global _workflow_service
	if _workflow_service is None:
		_workflow_service = WorkflowService(tool_dispatcher=get_tool_dispatcher())
	return _workflow_service


def get_chat_service() -> ChatService:
	global _chat_service
	if _chat_service is None:
		from app.agent.chat_agent import ChatAgent

		dispatcher = get_tool_dispatcher()
		agent = ChatAgent(tool_dispatcher=dispatcher)
		_chat_service = ChatService(
			agent=agent,
			workflow_service=get_workflow_service(),
		)
	return _chat_service