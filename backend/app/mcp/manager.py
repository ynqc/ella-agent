"""MCP client manager: connects to MCP servers, discovers tools, routes calls."""

import json
import logging
from pathlib import Path
from typing import Any

try:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client
    _mcp_import_error: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:
    Client = Any
    StdioServerParameters = Any
    stdio_client = None
    _mcp_import_error = exc

from app.tools.base import build_tool_response

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "mcp_servers.json"


class MCPManager:
    """Manages connections to multiple MCP servers and aggregates their tools."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._clients: dict[str, Client] = {}
        self._tools: list[dict[str, Any]] = []
        self._tool_routing: dict[str, str] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _load_config(self) -> dict[str, Any]:
        if not self._config_path.exists():
            logger.warning("MCP config not found at %s, no servers will be loaded", self._config_path)
            return {"servers": {}}
        text = self._config_path.read_text(encoding="utf-8")
        return json.loads(text)

    async def connect(self) -> None:
        if _mcp_import_error is not None:
            raise RuntimeError(
                "The optional 'mcp' package is not installed. Install dependencies with 'pip install -r requirements.txt'."
            ) from _mcp_import_error

        config = self._load_config()
        servers = config.get("servers", {})

        for server_id, server_config in servers.items():
            if not server_config.get("enabled", True):
                logger.info("MCP server '%s' is disabled, skipping", server_id)
                continue

            try:
                await self._connect_server(server_id, server_config)
            except Exception as exc:
                logger.error("Failed to connect MCP server '%s': %s", server_id, exc)

        self._connected = True
        logger.info(
            "MCP manager connected: %d servers, %d tools discovered",
            len(self._clients),
            len(self._tools),
        )

    async def _connect_server(self, server_id: str, config: dict[str, Any]) -> None:
        command = config["command"]
        args = config.get("args", [])
        env = config.get("env") or None
        cwd = config.get("cwd") or None

        params = StdioServerParameters(command=command, args=args, env=env, cwd=cwd)
        transport = stdio_client(params)
        client = Client(transport)
        await client.__aenter__()

        tools_result = await client.list_tools()
        self._clients[server_id] = client

        for tool in tools_result.tools:
            prefixed_name = f"{server_id}__{tool.name}"
            self._tool_routing[prefixed_name] = server_id
            self._tools.append({
                "name": prefixed_name,
                "description": tool.description or "",
                "group": f"mcp:{server_id}",
                "is_visible": True,
                "is_enabled": True,
                "input_schema": tool.input_schema or {"type": "object", "properties": {}},
                "output_schema": {},
            })

        logger.info(
            "MCP server '%s' connected: %d tools discovered",
            server_id,
            len(tools_result.tools),
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools)

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_routing

    async def call_tool(self, prefixed_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        server_id = self._tool_routing.get(prefixed_name)
        if server_id is None:
            return build_tool_response(
                prefixed_name, arguments or {}, [], status="error", error=f"Unknown MCP tool: {prefixed_name}"
            )

        original_name = prefixed_name[len(server_id) + 2:]
        client = self._clients[server_id]

        try:
            result = await client.call_tool(original_name, arguments)
        except Exception as exc:
            logger.error("MCP tool call failed (%s/%s): %s", server_id, original_name, exc)
            return build_tool_response(
                prefixed_name, arguments or {}, [], status="error", error=str(exc)
            )

        if result.is_error:
            error_text = self._extract_text(result.content)
            return build_tool_response(
                prefixed_name, arguments or {}, [], status="error", error=error_text
            )

        text_content = self._extract_text(result.content)
        try:
            data = json.loads(text_content)
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                data = [{"result": data}]
        except (json.JSONDecodeError, TypeError):
            data = [{"text": text_content}]

        return build_tool_response(prefixed_name, arguments or {}, data)

    def _extract_text(self, content: list) -> str:
        parts = []
        for block in content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts)

    async def shutdown(self) -> None:
        for server_id, client in self._clients.items():
            try:
                await client.__aexit__(None, None, None)
                logger.info("MCP server '%s' disconnected", server_id)
            except Exception as exc:
                logger.warning("Error disconnecting MCP server '%s': %s", server_id, exc)
        self._clients.clear()
        self._tools.clear()
        self._tool_routing.clear()
        self._connected = False
