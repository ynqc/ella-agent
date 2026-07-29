from typing import Any

from app.tools.base import BaseTool
from app.tools.browser import BrowserTool
from app.tools.calendar import CalendarTool
from app.tools.confluence import ConfluenceTool
from app.tools.filesystem import FilesystemTool
from app.tools.github import GithubTool
from app.tools.jira import JiraTool, PostJiraCommentTool
from app.tools.teams import SendTeamsMessageTool, TeamsTool


def build_tool_instances() -> list[BaseTool]:
	return [
		BrowserTool(),
		CalendarTool(),
		ConfluenceTool(),
		FilesystemTool(),
		GithubTool(),
		JiraTool(),
		PostJiraCommentTool(),
		TeamsTool(),
		SendTeamsMessageTool(),
	]


class ToolRegistry:
	def __init__(self, tools: list[BaseTool] | None = None) -> None:
		tool_instances = tools or build_tool_instances()
		self._tools: dict[str, BaseTool] = {}

		for tool in tool_instances:
			if tool.name in self._tools:
				raise ValueError(f"Duplicate tool name registered: {tool.name}")
			self._tools[tool.name] = tool

	def get(self, tool_name: str) -> BaseTool | None:
		return self._tools.get(tool_name)

	def all(
		self,
		*,
		groups: list[str] | None = None,
		visible_only: bool = False,
		enabled_only: bool = False,
	) -> list[BaseTool]:
		selected_groups = set(groups or [])
		tools: list[BaseTool] = []

		for tool in self._tools.values():
			if selected_groups and tool.group not in selected_groups:
				continue
			if visible_only and not tool.is_visible:
				continue
			if enabled_only and not tool.is_enabled:
				continue
			tools.append(tool)

		return tools

	def list_groups(self) -> list[str]:
		return sorted({tool.group for tool in self._tools.values()})

	def list_tools(
		self,
		*,
		groups: list[str] | None = None,
		visible_only: bool = False,
		enabled_only: bool = False,
	) -> list[dict[str, Any]]:
		return [
			{
				"name": tool.name,
				"description": tool.description,
				"group": tool.group,
				"is_visible": tool.is_visible,
				"is_enabled": tool.is_enabled,
				"input_schema": tool.input_schema,
				"output_schema": tool.output_schema,
			}
			for tool in self.all(
				groups=groups,
				visible_only=visible_only,
				enabled_only=enabled_only,
			)
		]