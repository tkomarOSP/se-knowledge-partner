from knowledge_repo.server import _SESSION_BASE, mcp

print(f"Knowledge Repository MCP — session base: {_SESSION_BASE}")
mcp.run(transport="streamable-http")
