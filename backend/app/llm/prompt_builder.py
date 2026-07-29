from dataclasses import dataclass
import json
from typing import Any

from config import settings


SYSTEM_TOOL_INSTRUCTIONS = (
	"You can call tools when they help answer the user. "
	"Choose the most appropriate tool from the provided schemas, then use the tool result to answer clearly."
)

MEMORY_EXTRACTION_INSTRUCTIONS = """Extract durable user memory from the message.
Return JSON only.
The output must be a JSON array.
Each item must be an object with these fields:
- memory_type: one of preference, profile, project, constraint
- content: a concise normalized fact in Chinese
- keywords: an array of short strings

Only extract facts that are likely useful in future turns.
Do not extract the user's transient request.
If there is no durable memory, return [] exactly.
"""


@dataclass(frozen=True)
class EffectiveUserMessageRequest:
	message: str
	memory_context: str


@dataclass(frozen=True)
class PlanningPromptRequest:
	message: str
	tools: list[dict[str, Any]]


@dataclass(frozen=True)
class MemoryExtractionPromptRequest:
	message: str


@dataclass(frozen=True)
class AssistantToolMessageRequest:
	assistant_content: str
	tool_calls: list[dict[str, Any]]


@dataclass(frozen=True)
class ToolFollowupPromptRequest:
	message: str
	tools: list[dict[str, Any]]
	assistant_content: str
	tool_calls: list[dict[str, Any]]
	tool_results: list[dict[str, Any]]


class PromptBuilder:
	def build_system_prompt(self, tools: list[dict[str, Any]]) -> str:
		available_tools = "\n".join(
			f"- {tool['name']}: {tool['description']}"
			for tool in tools
		)
		return (
			f"{settings.system_prompt}\n\n"
			f"{SYSTEM_TOOL_INSTRUCTIONS}\n"
			f"Available tools:\n{available_tools}"
		)

	def build_effective_user_message(self, request: EffectiveUserMessageRequest) -> str:
		if not request.memory_context:
			return request.message
		return f"[Memory Context]\n{request.memory_context}\n\n[User Message]\n{request.message}"

	def build_planning_messages(self, request: PlanningPromptRequest) -> list[dict[str, str]]:
		return [
			{"role": "system", "content": self.build_system_prompt(request.tools)},
			{"role": "user", "content": request.message},
		]

	def build_memory_extraction_messages(self, request: MemoryExtractionPromptRequest) -> list[dict[str, str]]:
		return [
			{"role": "system", "content": MEMORY_EXTRACTION_INSTRUCTIONS},
			{"role": "user", "content": request.message},
		]

	def build_assistant_tool_message(self, request: AssistantToolMessageRequest) -> dict[str, Any]:
		return {
			"role": "assistant",
			"content": request.assistant_content,
			"tool_calls": [
				{
					"id": tool_call["id"],
					"type": "function",
					"function": {
						"name": tool_call["name"],
						"arguments": json.dumps(tool_call["args"], ensure_ascii=False),
					},
				}
				for tool_call in request.tool_calls
			],
		}

	def build_tool_followup_messages(self, request: ToolFollowupPromptRequest) -> list[dict[str, Any]]:
		messages: list[dict[str, Any]] = self.build_planning_messages(
			PlanningPromptRequest(message=request.message, tools=request.tools)
		)
		messages.append(
			self.build_assistant_tool_message(
				AssistantToolMessageRequest(
					assistant_content=request.assistant_content,
					tool_calls=request.tool_calls,
				)
			)
		)

		for tool_call, result in zip(request.tool_calls, request.tool_results, strict=True):
			messages.append(
				{
					"role": "tool",
					"tool_call_id": tool_call["id"],
					"content": json.dumps(result, ensure_ascii=False),
				}
			)

		return messages