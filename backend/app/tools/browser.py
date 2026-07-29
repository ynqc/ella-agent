from app.tools.base import BaseTool, COMMON_OUTPUT_SCHEMA, build_tool_response, string_parameter_schema


class BrowserTool(BaseTool):
	name = "search_browser"
	description = "Search browser content and return mock web results."
	group = "research"
	input_schema = {
		"type": "object",
		"properties": {
			"query": string_parameter_schema("Browser search keywords.", "ella agent"),
		},
		"required": [],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		query = normalized_params["query"]
		data = [
			{
				"title": "Ella Agent Overview",
				"url": "https://example.com/ella-agent-overview",
				"snippet": f"Top browser result for '{query}'.",
			},
			{
				"title": "Ella Agent Runbook",
				"url": "https://example.com/ella-agent-runbook",
				"snippet": "Mock runbook page with setup and workflow notes.",
			},
		]
		return build_tool_response(self.name, normalized_params, data)


__all__ = ["BrowserTool"]