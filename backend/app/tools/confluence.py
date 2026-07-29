from app.tools.base import BaseTool, COMMON_OUTPUT_SCHEMA, build_tool_response, string_parameter_schema


class ConfluenceTool(BaseTool):
	name = "search_confluence"
	description = "Search Confluence pages and return mock documents."
	group = "knowledge"
	input_schema = {
		"type": "object",
		"properties": {
			"query": string_parameter_schema("Confluence search keywords.", "engineering handbook"),
		},
		"required": [],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		query = normalized_params["query"]
		data = [
			{
				"title": "Engineering Handbook",
				"space": "ENG",
				"url": "https://example.com/confluence/ENG/engineering-handbook",
				"summary": f"Mock Confluence result related to '{query}'.",
			},
			{
				"title": "Incident Response Guide",
				"space": "OPS",
				"url": "https://example.com/confluence/OPS/incident-response-guide",
				"summary": "Mock operations guide for incident handling.",
			},
		]
		return build_tool_response(self.name, normalized_params, data)


__all__ = ["ConfluenceTool"]