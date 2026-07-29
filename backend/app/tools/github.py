from app.tools.base import BaseTool, COMMON_OUTPUT_SCHEMA, build_tool_response, string_parameter_schema


class GithubTool(BaseTool):
	name = "search_github_prs"
	description = "Search GitHub pull requests and return mock results."
	group = "engineering"
	input_schema = {
		"type": "object",
		"properties": {
			"repository": string_parameter_schema(
				"Repository name in owner/repo format.",
				"My-Project/ella-agent",
			),
		},
		"required": [],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		repository = normalized_params["repository"]
		data = [
			{
				"id": "PR-142",
				"title": "Add mock tool dispatcher",
				"repository": repository,
				"status": "open",
			},
			{
				"id": "PR-137",
				"title": "Refactor chat streaming client",
				"repository": repository,
				"status": "merged",
			},
		]
		return build_tool_response(self.name, normalized_params, data)


__all__ = ["GithubTool"]