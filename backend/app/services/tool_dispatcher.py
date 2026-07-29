from typing import Any

from app.tools.base import build_tool_response
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry


class ToolDispatcher:
	def __init__(self, registry: ToolRegistry | None = None) -> None:
		self._registry = registry or ToolRegistry()

	def list_tools(self) -> list[dict[str, Any]]:
		return self._registry.list_tools()

	def dispatch(self, tool_name: str, params: dict | None = None) -> dict[str, Any]:
		tool = self._registry.get(tool_name)
		if tool is None:
			return build_tool_response(
				tool_name,
				params or {},
				[],
				status="error",
				error=f"Unknown tool: {tool_name}",
			)

		try:
			normalized_params = self._normalize_params(tool.input_schema, params)
		except ValueError as exc:
			return build_tool_response(
				tool_name,
				params or {},
				[],
				status="error",
				error=str(exc),
			)

		return tool.execute(normalized_params)

	def _normalize_params(
		self,
		schema: dict[str, Any],
		params: dict[str, Any] | None,
	) -> dict[str, Any]:
		raw_params = params or {}
		if not isinstance(raw_params, dict):
			raise ValueError("Tool params must be a JSON object.")

		properties = schema.get("properties", {})
		required = schema.get("required", [])
		normalized: dict[str, Any] = {}

		for name in required:
			if name not in raw_params and "default" not in properties.get(name, {}):
				raise ValueError(f"Missing required parameter: {name}")

		for name, spec in properties.items():
			value = raw_params.get(name, spec.get("default"))
			if value is None:
				continue

			expected_type = spec.get("type")
			if expected_type == "string" and not isinstance(value, str):
				raise ValueError(f"Parameter '{name}' must be a string.")

			normalized[name] = value

		unknown_params = set(raw_params) - set(properties)
		if unknown_params:
			names = ", ".join(sorted(unknown_params))
			raise ValueError(f"Unknown parameter(s): {names}")

		return normalized