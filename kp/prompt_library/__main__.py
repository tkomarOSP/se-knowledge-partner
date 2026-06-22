from prompt_library.server import _SESSION_BASE, mcp

print(f"Prompt Library MCP — session base: {_SESSION_BASE}")
mcp.run(transport="streamable-http")
