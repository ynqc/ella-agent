from app.tools.base import BaseTool, COMMON_OUTPUT_SCHEMA, build_tool_response, string_parameter_schema


class JiraTool(BaseTool):
	name = "get_my_jiras"
	description = "Get current user's Jira tasks."
	group = "engineering"
	input_schema = {
		"type": "object",
		"properties": {
			"assignee": string_parameter_schema("Jira assignee identifier.", "me"),
		},
		"required": [],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		assignee = normalized_params["assignee"]
		data = [
			{
				"key": "ITL-829",
				"summary": "Implement mock tool dispatcher",
				"status": "In Progress",
				"assignee": assignee,
			},
			{
				"key": "ITL-830",
				"summary": "Add mock integrations for collaboration tools",
				"status": "Todo",
				"assignee": assignee,
			},
		]
		return build_tool_response(self.name, normalized_params, data)


class PostJiraCommentTool(BaseTool):
	name = "post_jira_comment"
	description = "Post a mock Jira comment to an issue."
	group = "engineering"
	input_schema = {
		"type": "object",
		"properties": {
			"issue_key": string_parameter_schema("Jira issue key.", "ITL-000"),
			"comment": {
				"type": "string",
				"description": "Comment body to post.",
			},
		},
		"required": ["issue_key", "comment"],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		issue_key = normalized_params["issue_key"]
		comment = normalized_params["comment"]
		data = [
			{
				"issue_key": issue_key,
				"comment": comment,
				"comment_id": f"jira-{abs(hash((issue_key, comment))) % 1000000:06d}",
				"status": "posted",
			}
		]
		return build_tool_response(self.name, normalized_params, data)


__all__ = ["JiraTool", "PostJiraCommentTool"]