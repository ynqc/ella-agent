"""Tests for MCPManager: config loading, tool discovery, routing, and call."""

import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.manager import MCPManager


@pytest.fixture
def tmp_config(tmp_path):
    config = {
        "servers": {
            "test-server": {
                "command": "python",
                "args": ["mcp_servers/mock_jira_server.py"],
                "env": {},
                "enabled": True,
            },
            "disabled-server": {
                "command": "python",
                "args": ["mcp_servers/mock_github_server.py"],
                "env": {},
                "enabled": False,
            },
        }
    }
    config_file = tmp_path / "mcp_servers.json"
    config_file.write_text(json.dumps(config))
    return config_file


@pytest.fixture
def empty_config(tmp_path):
    config_file = tmp_path / "mcp_servers.json"
    config_file.write_text(json.dumps({"servers": {}}))
    return config_file


class TestMCPManagerConfig:
    def test_load_config_with_servers(self, tmp_config):
        manager = MCPManager(config_path=tmp_config)
        config = manager._load_config()
        assert "servers" in config
        assert "test-server" in config["servers"]
        assert config["servers"]["disabled-server"]["enabled"] is False

    def test_load_config_missing_file(self, tmp_path):
        manager = MCPManager(config_path=tmp_path / "nonexistent.json")
        config = manager._load_config()
        assert config == {"servers": {}}

    def test_load_empty_config(self, empty_config):
        manager = MCPManager(config_path=empty_config)
        config = manager._load_config()
        assert config["servers"] == {}


class TestMCPManagerConnection:
    @pytest.mark.asyncio
    async def test_connect_discovers_tools(self):
        manager = MCPManager()
        await manager.connect()
        try:
            assert manager.connected is True
            tools = manager.list_tools()
            assert len(tools) == 6
            tool_names = [t["name"] for t in tools]
            assert "mock-jira__jira_search_issues" in tool_names
            assert "mock-github__github_list_prs" in tool_names
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_disabled_server_not_connected(self, tmp_config):
        manager = MCPManager(config_path=tmp_config)
        await manager.connect()
        try:
            assert manager.connected is True
            tool_names = [t["name"] for t in manager.list_tools()]
            assert any("test-server__" in n for n in tool_names)
            assert not any("disabled-server__" in n for n in tool_names)
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_connect_with_no_servers(self, empty_config):
        manager = MCPManager(config_path=empty_config)
        await manager.connect()
        try:
            assert manager.connected is True
            assert manager.list_tools() == []
        finally:
            await manager.shutdown()


class TestMCPManagerToolRouting:
    @pytest.mark.asyncio
    async def test_has_tool(self):
        manager = MCPManager()
        await manager.connect()
        try:
            assert manager.has_tool("mock-jira__jira_search_issues") is True
            assert manager.has_tool("mock-github__github_list_prs") is True
            assert manager.has_tool("nonexistent") is False
            assert manager.has_tool("jira_search_issues") is False
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_tool_name_prefix_format(self):
        manager = MCPManager()
        await manager.connect()
        try:
            for tool in manager.list_tools():
                assert "__" in tool["name"]
                server_id, original_name = tool["name"].split("__", 1)
                assert server_id in ("mock-jira", "mock-github")
                assert original_name
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_tool_schema_format(self):
        manager = MCPManager()
        await manager.connect()
        try:
            for tool in manager.list_tools():
                assert "name" in tool
                assert "description" in tool
                assert "input_schema" in tool
                assert "group" in tool
                assert tool["group"].startswith("mcp:")
                assert tool["is_visible"] is True
                assert tool["is_enabled"] is True
        finally:
            await manager.shutdown()


class TestMCPManagerCallTool:
    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        manager = MCPManager()
        await manager.connect()
        try:
            result = await manager.call_tool("mock-jira__jira_search_issues", {"query": "login"})
            assert result["status"] == "success"
            assert result["tool"] == "mock-jira__jira_search_issues"
            assert isinstance(result["data"], list)
            assert len(result["data"]) > 0
            assert result["error"] is None
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_call_tool_unknown(self):
        manager = MCPManager()
        await manager.connect()
        try:
            result = await manager.call_tool("nonexistent__tool", {})
            assert result["status"] == "error"
            assert "Unknown MCP tool" in result["error"]
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_call_tool_with_args(self):
        manager = MCPManager()
        await manager.connect()
        try:
            result = await manager.call_tool(
                "mock-jira__jira_create_issue",
                {"project": "TEAM", "summary": "Test issue", "description": "A test"},
            )
            assert result["status"] == "success"
            data = result["data"][0]
            assert data["created"] is True
            assert data["issue"]["summary"] == "Test issue"
        finally:
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_call_github_tool(self):
        manager = MCPManager()
        await manager.connect()
        try:
            result = await manager.call_tool(
                "mock-github__github_get_pr",
                {"repo": "myorg/myrepo", "pr_number": 142},
            )
            assert result["status"] == "success"
            data = result["data"][0]
            assert "pull_request" in data
            assert data["pull_request"]["number"] == 142
        finally:
            await manager.shutdown()


class TestMCPManagerShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_clears_state(self):
        manager = MCPManager()
        await manager.connect()
        assert manager.connected is True
        assert len(manager.list_tools()) > 0

        await manager.shutdown()
        assert manager.connected is False
        assert manager.list_tools() == []
        assert manager.has_tool("mock-jira__jira_search_issues") is False
