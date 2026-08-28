"""Tests for ToolDispatcher MCP integration: merged listing, routing, dispatch."""

import asyncio

import pytest
import pytest_asyncio

from app.mcp.manager import MCPManager
from app.services.tool_dispatcher import ToolDispatcher
from app.tools.registry import ToolRegistry


@pytest_asyncio.fixture
async def mcp_manager():
    manager = MCPManager()
    await manager.connect()
    yield manager
    await manager.shutdown()


@pytest.fixture
def dispatcher_with_mcp(mcp_manager):
    registry = ToolRegistry()
    return ToolDispatcher(registry=registry, mcp_manager=mcp_manager)


@pytest.fixture
def dispatcher_without_mcp():
    registry = ToolRegistry()
    return ToolDispatcher(registry=registry, mcp_manager=None)


class TestToolDispatcherListTools:
    @pytest.mark.asyncio
    async def test_list_tools_includes_local_and_mcp(self, dispatcher_with_mcp):
        tools = dispatcher_with_mcp.list_tools()
        tool_names = [t["name"] for t in tools]
        # Local tools still present
        assert "search_browser" in tool_names
        assert "get_my_jiras" in tool_names
        # MCP tools added
        assert "mock-jira__jira_search_issues" in tool_names
        assert "mock-github__github_list_prs" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_count_is_sum(self, dispatcher_with_mcp):
        tools = dispatcher_with_mcp.list_tools()
        local_count = len(ToolRegistry().list_tools())
        mcp_count = 6  # 3 jira + 3 github
        assert len(tools) == local_count + mcp_count

    def test_list_tools_without_mcp(self, dispatcher_without_mcp):
        tools = dispatcher_without_mcp.list_tools()
        local_count = len(ToolRegistry().list_tools())
        assert len(tools) == local_count


class TestToolDispatcherMCPRouting:
    @pytest.mark.asyncio
    async def test_dispatch_mcp_tool(self, dispatcher_with_mcp):
        result = await dispatcher_with_mcp.dispatch(
            "mock-jira__jira_search_issues", {"query": "test"}
        )
        assert result["status"] == "success"
        assert result["tool"] == "mock-jira__jira_search_issues"
        assert isinstance(result["data"], list)

    @pytest.mark.asyncio
    async def test_dispatch_local_tool(self, dispatcher_with_mcp):
        result = await dispatcher_with_mcp.dispatch(
            "search_browser", {"query": "hello"}
        )
        assert result["tool"] == "search_browser"
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self, dispatcher_with_mcp):
        result = await dispatcher_with_mcp.dispatch("totally_fake_tool", {})
        assert result["status"] == "error"
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_dispatch_without_mcp_local_only(self, dispatcher_without_mcp):
        result = await dispatcher_without_mcp.dispatch(
            "search_browser", {"query": "hello"}
        )
        assert result["tool"] == "search_browser"
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_dispatch_without_mcp_mcp_tool_unknown(self, dispatcher_without_mcp):
        result = await dispatcher_without_mcp.dispatch(
            "mock-jira__jira_search_issues", {"query": "test"}
        )
        assert result["status"] == "error"
        assert "Unknown tool" in result["error"]


class TestToolDispatcherMCPResults:
    @pytest.mark.asyncio
    async def test_mcp_result_format_matches_local(self, dispatcher_with_mcp):
        result = await dispatcher_with_mcp.dispatch(
            "mock-jira__jira_create_issue",
            {"project": "TEST", "summary": "Hello"},
        )
        # Should match build_tool_response format
        assert "tool" in result
        assert "status" in result
        assert "input" in result
        assert "data" in result
        assert "error" in result
        assert result["status"] == "success"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_mcp_github_tool_returns_data(self, dispatcher_with_mcp):
        result = await dispatcher_with_mcp.dispatch(
            "mock-github__github_list_prs",
            {"repo": "org/repo", "state": "open"},
        )
        assert result["status"] == "success"
        data = result["data"][0]
        assert "pull_requests" in data
        assert len(data["pull_requests"]) == 3
