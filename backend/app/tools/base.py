from abc import ABC, abstractmethod
from typing import Any


COMMON_OUTPUT_SCHEMA = {
	"type": "object",
	"properties": {
		"tool": {"type": "string"},
		"status": {"type": "string", "enum": ["success", "error"]},
		"input": {"type": "object"},
		"data": {"type": "array", "items": {"type": "object"}},
		"error": {"type": ["string", "null"]},
	},
	"required": ["tool", "status", "input", "data", "error"],
}


class BaseTool(ABC):
	name: str
	description: str
	input_schema: dict[str, Any]
	output_schema: dict[str, Any] = COMMON_OUTPUT_SCHEMA
	group: str = "general"
	is_visible: bool = True
	is_enabled: bool = True

	@abstractmethod
	def execute(self, params: dict | None = None) -> dict[str, Any]:
		raise NotImplementedError


def build_tool_response(
	tool_name: str,
	params: dict[str, Any],
	data: list[dict[str, Any]],
	*,
	status: str = "success",
	error: str | None = None,
) -> dict[str, Any]:
	return {
		"tool": tool_name,
		"status": status,
		"input": params,
		"data": data,
		"error": error,
	}


def string_parameter_schema(description: str, default: str) -> dict[str, str]:
	return {
		"type": "string",
		"description": description,
		"default": default,
	}


__all__ = ["BaseTool", "COMMON_OUTPUT_SCHEMA", "build_tool_response", "string_parameter_schema"]