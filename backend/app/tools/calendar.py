from app.tools.base import BaseTool, COMMON_OUTPUT_SCHEMA, build_tool_response, string_parameter_schema


class CalendarTool(BaseTool):
	name = "get_my_calendar"
	description = "Get current user's calendar events."
	group = "collaboration"
	input_schema = {
		"type": "object",
		"properties": {
			"date": string_parameter_schema("ISO date for the schedule.", "2026-07-20"),
		},
		"required": [],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		date = normalized_params["date"]
		data = [
			{
				"title": "Daily Standup",
				"start": f"{date}T09:30:00",
				"end": f"{date}T10:00:00",
				"location": "Teams",
			},
			{
				"title": "Sprint Planning",
				"start": f"{date}T14:00:00",
				"end": f"{date}T15:00:00",
				"location": "Meeting Room A",
			},
		]
		return build_tool_response(self.name, normalized_params, data)


__all__ = ["CalendarTool"]