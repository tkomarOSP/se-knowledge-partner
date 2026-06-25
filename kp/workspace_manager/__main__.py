from workspace_manager.server import _SESSION_BASE, mcp

print(f"Workspace Manager MCP — session base: {_SESSION_BASE}")
mcp.run(transport="streamable-http")
