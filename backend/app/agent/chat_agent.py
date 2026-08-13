import logging

from app.agent.hooks import AgentRuntimeHook
from collections.abc import AsyncIterator

from app.agent.runtime import AgentRuntime
from app.agent.state import AgentRunResult, AgentState
from app.llm.client import LLMClient
from app.memory.memory_manager import MemoryManager
from app.services.tool_dispatcher import ToolDispatcher
from app.services.knowledge_service import KnowledgeService


class ChatAgent:
	"""Agent responsible for orchestrating chat responses."""

	def __init__(
		self,
		tool_dispatcher: ToolDispatcher | None = None,
		llm_client: LLMClient | None = None,
		logger: logging.Logger | None = None,
		memory_manager: MemoryManager | None = None,
		runtime_hooks: list[AgentRuntimeHook] | None = None,
		knowledge_service: KnowledgeService | None = None,
	) -> None:
		self._tool_dispatcher = tool_dispatcher or ToolDispatcher()
		self._logger = logger or logging.getLogger(__name__)
		self._llm_client = llm_client or LLMClient(self._logger)
		self._memory_manager = memory_manager or MemoryManager()
		self._runtime_hooks = runtime_hooks or []
		self._knowledge_service = knowledge_service or KnowledgeService()

	def _build_runtime(self) -> AgentRuntime:
		return AgentRuntime(
			tool_dispatcher=self._tool_dispatcher,
			llm_client=self._llm_client,
			memory_manager=self._memory_manager,
			logger=self._logger,
			hooks=self._runtime_hooks,
			knowledge_service=self._knowledge_service,
		)

	async def run(self, session_id: str, message: str) -> AgentRunResult:
		state = AgentState(session_id=session_id, user_message=message.strip())
		return await self._build_runtime().run(state)

	async def stream_response(self, session_id: str, message: str) -> AsyncIterator[str]:
		state = AgentState(session_id=session_id, user_message=message.strip())
		async for text in self._build_runtime().stream(state):
			yield text