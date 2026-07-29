import json
import logging
from typing import Any

from config import settings

from app.llm.prompt_builder import (
	MemoryExtractionPromptRequest,
	PlanningPromptRequest,
	PromptBuilder,
	ToolFollowupPromptRequest,
)


class LLMClient:
	def __init__(
		self,
		logger: logging.Logger | None = None,
		prompt_builder: PromptBuilder | None = None,
	) -> None:
		self._logger = logger or logging.getLogger(__name__)
		self._prompt_builder = prompt_builder or PromptBuilder()

	@property
	def prompt_builder(self) -> PromptBuilder:
		return self._prompt_builder

	def build_planning_messages(self, message: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
		return self._prompt_builder.build_planning_messages(
			PlanningPromptRequest(message=message, tools=tools)
		)

	async def invoke_text(self, messages: list[dict[str, Any]]) -> str:
		llm = self._build_llm()
		response = await llm.ainvoke(messages)
		return self.response_text(response)

	def _build_llm(self) -> Any:
		from langchain_openai import ChatOpenAI

		if not settings.ssnc_api_key:
			raise RuntimeError("SSC_CLOUD_API_KEY is not set")

		if not settings.ssnc_case_id:
			raise RuntimeError("SSNC_CASE_ID is not set")

		return ChatOpenAI(
			model=settings.ssnc_model,
			temperature=settings.ssnc_temperature,
			api_key=settings.ssnc_api_key,
			base_url=settings.ssnc_base_url,
			streaming=True,
			default_headers={"OpenAI-Project": settings.ssnc_case_id},
		)

	def build_tool_schemas(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
		return [
			{
				"type": "function",
				"function": {
					"name": tool["name"],
					"description": tool["description"],
					"parameters": tool["input_schema"],
				},
			}
			for tool in tools
		]

	def build_memory_extraction_messages(self, message: str) -> list[dict[str, Any]]:
		return self._prompt_builder.build_memory_extraction_messages(
			MemoryExtractionPromptRequest(message=message)
		)

	def build_tool_followup_messages(
		self,
		message: str,
		tools: list[dict[str, Any]],
		planning_response: Any,
		tool_calls: list[dict[str, Any]],
		tool_results: list[dict[str, Any]],
	) -> list[dict[str, Any]]:
		return self._prompt_builder.build_tool_followup_messages(
			ToolFollowupPromptRequest(
				message=message,
				tools=tools,
				assistant_content=self.response_text(planning_response),
				tool_calls=tool_calls,
				tool_results=tool_results,
			)
		)

	def response_text(self, response: Any) -> str:
		return self._coerce_chunk_text(getattr(response, "content", ""))

	def _coerce_chunk_text(self, content: object) -> str:
		if isinstance(content, str):
			return content
		if isinstance(content, list):
			parts: list[str] = []
			for item in content:
				if isinstance(item, str):
					parts.append(item)
				elif isinstance(item, dict):
					text = item.get("text")
					if isinstance(text, str):
						parts.append(text)
			return "".join(parts)
		return ""

	def _normalize_tool_call_args(self, raw_args: object) -> dict[str, object]:
		if raw_args is None:
			return {}
		if isinstance(raw_args, dict):
			return raw_args
		if isinstance(raw_args, str):
			try:
				parsed = json.loads(raw_args)
			except json.JSONDecodeError as exc:
				raise ValueError(f"Invalid tool args JSON: {exc.msg}") from exc
			if not isinstance(parsed, dict):
				raise ValueError("Tool args must decode to a JSON object.")
			return parsed
		raise ValueError("Tool args must be a JSON object.")

	def _strip_code_fence(self, text: str) -> str:
		stripped = text.strip()
		if not stripped.startswith("```"):
			return stripped

		lines = stripped.splitlines()
		if len(lines) >= 2 and lines[-1].strip() == "```":
			return "\n".join(lines[1:-1]).strip()
		return stripped

	def _parse_memory_payload(self, text: str) -> list[dict[str, object]]:
		payload = self._strip_code_fence(text)
		parsed = json.loads(payload)
		if not isinstance(parsed, list):
			raise ValueError("Extracted memories must be a JSON array.")

		memories: list[dict[str, object]] = []
		for item in parsed:
			if isinstance(item, dict):
				memories.append(item)
		return memories

	async def extract_memories(self, message: str) -> list[dict[str, object]]:
		llm = self._build_llm()
		response = await llm.ainvoke(self.build_memory_extraction_messages(message))
		text = self.response_text(response)
		if not text.strip():
			return []
		return self._parse_memory_payload(text)

	def extract_tool_calls(self, response: Any) -> list[dict[str, Any]]:
		raw_tool_calls = getattr(response, "tool_calls", None) or []
		tool_calls: list[dict[str, Any]] = []

		for index, tool_call in enumerate(raw_tool_calls):
			name = tool_call.get("name")
			if not isinstance(name, str) or not name:
				continue

			tool_calls.append(
				{
					"id": tool_call.get("id") or f"tool_call_{index}",
					"name": name,
					"args": self._normalize_tool_call_args(tool_call.get("args")),
				}
			)

		return tool_calls

	async def stream_final_answer(
		self,
		llm_with_tools: Any,
		message: str,
		tools: list[dict[str, Any]],
		planning_response: Any,
		tool_calls: list[dict[str, Any]],
		tool_results: list[dict[str, Any]],
		followup_messages: list[dict[str, Any]] | None = None,
	):
		messages = followup_messages or self.build_tool_followup_messages(
			message=message,
			tools=tools,
			planning_response=planning_response,
			tool_calls=tool_calls,
			tool_results=tool_results,
		)
		self._logger.info("requesting final answer from llm with tool results")
		async for chunk in llm_with_tools.astream(messages):
			text = self._coerce_chunk_text(chunk.content)
			if text:
				yield text