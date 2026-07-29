from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeAlias

from pydantic import BaseModel

from app.llm.client import LLMClient
from app.memory.memory_manager import MemoryManager
from app.services.tool_dispatcher import ToolDispatcher
from app.workflows.base import WorkflowRunResult
from app.workflows.bug import BugWorkflow
from app.workflows.contracts import BugWorkflowInput, MeetingWorkflowInput
from app.workflows.meeting import MeetingWorkflow


class WorkflowExecutor(Protocol):
	workflow_type: str

	async def run(self, **kwargs: Any) -> WorkflowRunResult:
		...


WorkflowFactory: TypeAlias = Callable[[], WorkflowExecutor]
WorkflowRunner: TypeAlias = Callable[..., Awaitable[WorkflowRunResult]]
WorkflowInputModel: TypeAlias = type[BaseModel]


class WorkflowRegistry:
	def __init__(self) -> None:
		self._factories: dict[str, WorkflowFactory] = {}
		self._runners: dict[str, WorkflowRunner] = {}
		self._input_models: dict[str, WorkflowInputModel] = {}

	def _normalize_workflow_type(self, workflow_type: str) -> str:
		normalized = workflow_type.strip()
		if not normalized:
			raise ValueError("Workflow type must be a non-empty string.")
		return normalized

	def register(self, workflow_type: str, factory: WorkflowFactory, *, input_model: WorkflowInputModel) -> None:
		workflow_type = self._normalize_workflow_type(workflow_type)
		if workflow_type in self._factories:
			raise ValueError(f"Workflow '{workflow_type}' is already registered.")
		self._factories[workflow_type] = factory
		self._input_models[workflow_type] = input_model

	def create(self, workflow_type: str) -> WorkflowExecutor:
		workflow_type = self._normalize_workflow_type(workflow_type)
		try:
			factory = self._factories[workflow_type]
		except KeyError as exc:
			raise ValueError(f"Workflow '{workflow_type}' is not registered.") from exc
		return factory()

	def register_runner(self, workflow_type: str, runner: WorkflowRunner) -> None:
		workflow_type = self._normalize_workflow_type(workflow_type)
		if workflow_type not in self._factories:
			raise ValueError(f"Workflow '{workflow_type}' must be registered before assigning a runner.")
		self._runners[workflow_type] = runner

	def validate_input(self, workflow_type: str, payload: dict[str, object]) -> BaseModel:
		workflow_type = self._normalize_workflow_type(workflow_type)
		try:
			model = self._input_models[workflow_type]
		except KeyError as exc:
			raise ValueError(f"Workflow '{workflow_type}' is not registered.") from exc
		return model.model_validate(payload)

	async def run(self, workflow_type: str, **kwargs: Any) -> WorkflowRunResult:
		workflow_type = self._normalize_workflow_type(workflow_type)
		runner = self._runners.get(workflow_type)
		if runner is not None:
			return await runner(**kwargs)
		workflow = self.create(workflow_type)
		return await workflow.run(**kwargs)

	def supports(self, workflow_type: str) -> bool:
		try:
			workflow_type = self._normalize_workflow_type(workflow_type)
		except ValueError:
			return False
		return workflow_type in self._factories

	def supported_workflow_types(self) -> tuple[str, ...]:
		return tuple(self._factories.keys())


def build_default_workflow_registry(
	*,
	llm_client: LLMClient,
	memory_manager: MemoryManager,
	tool_dispatcher: ToolDispatcher,
) -> WorkflowRegistry:
	registry = WorkflowRegistry()
	registry.register(
		MeetingWorkflow.workflow_type,
		lambda: MeetingWorkflow(
			llm_client=llm_client,
			memory_manager=memory_manager,
			tool_dispatcher=tool_dispatcher,
		),
		input_model=MeetingWorkflowInput,
	)
	registry.register(
		BugWorkflow.workflow_type,
		lambda: BugWorkflow(
			llm_client=llm_client,
			tool_dispatcher=tool_dispatcher,
		),
		input_model=BugWorkflowInput,
	)
	return registry