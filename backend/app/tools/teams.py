from app.tools.base import BaseTool, COMMON_OUTPUT_SCHEMA, build_tool_response, string_parameter_schema


class TeamsTool(BaseTool):
	name = "get_recent_teams_messages"
	description = "Get mock recent Microsoft Teams messages."
	group = "collaboration"
	input_schema = {
		"type": "object",
		"properties": {
			"channel": string_parameter_schema("Teams channel name.", "engineering"),
		},
		"required": [],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		channel = normalized_params["channel"]
		data = [
			{
				"channel": channel,
				"from": "Alice",
				"message": "Please review the mock tool integration changes.",
				"timestamp": "2026-07-20T10:15:00",
			},
			{
				"channel": channel,
				"from": "Bob",
				"message": "Sprint planning slides are ready.",
				"timestamp": "2026-07-20T11:05:00",
			},
		]
		return build_tool_response(self.name, normalized_params, data)


class SendTeamsMessageTool(BaseTool):
	name = "send_teams_message"
	description = "Send a mock Microsoft Teams message to a channel."
	group = "collaboration"
	input_schema = {
		"type": "object",
		"properties": {
			"channel": string_parameter_schema("Teams channel name.", "engineering"),
			"message": {
				"type": "string",
				"description": "Message body to send.",
			},
		},
		"required": ["message"],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		channel = normalized_params["channel"]
		message = normalized_params["message"]
		data = [
			{
				"channel": channel,
				"message": message,
				"delivery_id": f"teams-{abs(hash((channel, message))) % 1000000:06d}",
				"status": "sent",
			}
		]
		return build_tool_response(self.name, normalized_params, data)


__all__ = ["SendTeamsMessageTool", "TeamsTool"]