"""Synchronous MCP client pool — fetches tool lists and dispatches calls."""

from __future__ import annotations

import json
from typing import Any

import httpx


class MCPClientPool:
    """Manages connections to one or more streamable-http MCP servers.

    Provides a synchronous interface so LangGraph tool nodes can call MCP
    tools without async machinery.
    """

    def __init__(self, servers: dict[str, str], timeout: float = 30.0):
        """
        Args:
            servers: Mapping of server name → MCP endpoint URL.
            timeout: HTTP request timeout in seconds.
        """
        self._servers = servers
        self._timeout = timeout
        self._tool_cache: dict[str, list[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def list_tools(self, server: str) -> list[dict[str, Any]]:
        """Return the tool manifest for a named server (cached after first call)."""
        if server in self._tool_cache:
            return self._tool_cache[server]

        url = self._servers[server]
        resp = httpx.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        tools = resp.json().get("result", {}).get("tools", [])
        self._tool_cache[server] = tools
        return tools

    def all_tools(self) -> list[dict[str, Any]]:
        """Return all tools from all registered servers, prefixed with server name."""
        result = []
        for server in self._servers:
            try:
                for tool in self.list_tools(server):
                    result.append({**tool, "_server": server, "name": f"{server}__{tool['name']}"})
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def call(self, server: str, tool: str, **kwargs: Any) -> Any:
        """Call a tool on a named server synchronously.

        Args:
            server: Server name as registered in the pool.
            tool: MCP tool name (without server prefix).
            **kwargs: Tool arguments.

        Returns:
            The ``result`` value from the MCP JSON-RPC response.

        Raises:
            httpx.HTTPStatusError: On HTTP failure.
            RuntimeError: If the MCP response contains an ``error`` field.
        """
        url = self._servers[server]
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": kwargs},
        }
        resp = httpx.post(url, json=payload, timeout=self._timeout)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"MCP error from {server}/{tool}: {body['error']}")
        return body.get("result")

    def call_by_prefixed_name(self, prefixed_name: str, **kwargs: Any) -> Any:
        """Call a tool using its ``server__tool_name`` prefixed form."""
        server, _, tool = prefixed_name.partition("__")
        return self.call(server, tool, **kwargs)
