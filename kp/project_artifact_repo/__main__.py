from project_artifact_repo.server import _SESSION_BASE, mcp

print(f"Project Artifact Repository MCP — session base: {_SESSION_BASE}")
mcp.run(transport="streamable-http")
