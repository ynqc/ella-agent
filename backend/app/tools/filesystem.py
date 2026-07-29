from app.tools.base import BaseTool, COMMON_OUTPUT_SCHEMA, build_tool_response, string_parameter_schema


class FilesystemTool(BaseTool):
	name = "list_files"
	description = "List files in a mock workspace directory."
	group = "workspace"
	input_schema = {
		"type": "object",
		"properties": {
			"path": string_parameter_schema("Workspace path to inspect.", "/workspace"),
		},
		"required": [],
	}
	output_schema = COMMON_OUTPUT_SCHEMA

	def execute(self, params: dict | None = None) -> dict[str, object]:
		normalized_params = params or {}
		path = normalized_params["path"]
		data = [
			{
				"name": "README.md",
				"path": f"{path}/README.md",
				"type": "file",
			},
			{
				"name": "api",
				"path": f"{path}/api",
				"type": "directory",
			},
			{
				"name": "tools",
				"path": f"{path}/tools",
				"type": "directory",
			},
		]
		return build_tool_response(self.name, normalized_params, data)


__all__ = ["FilesystemTool"]