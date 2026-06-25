"""MCP tool implementations for workspace lifecycle.

Thin wrappers around WorkspaceStore — see store/workspace_store.py for the
actual branch/manifest/status logic.
"""

from __future__ import annotations

from typing import Any, Optional

from workspace_manager.store.git_store import GitStore
from workspace_manager.store.workspace_store import WorkspaceStore


def tool_create_workspace(store: GitStore, routine_id: str, engineer: Optional[str] = None) -> dict[str, Any]:
    """Create a new workspace branch (workspace/{routine_id}-{date}) and its manifest."""
    return WorkspaceStore(store).create(routine_id, engineer)


def tool_write_workspace_artifact(
    store: GitStore,
    branch_name: str,
    package: str,
    type: str,
    name: str,
    content_str: str,
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Write a typed artifact into a workspace branch, committed immediately."""
    return WorkspaceStore(store).write_workspace_artifact(branch_name, package, type, name, content_str, tags)


def tool_read_workspace_artifact(store: GitStore, branch_name: str, output_name: str) -> dict[str, Any]:
    """Read one workspace output's content via `git show` — does not check out the branch."""
    return WorkspaceStore(store).read_workspace_artifact(branch_name, output_name)


def tool_list_workspaces(store: GitStore) -> list[dict[str, Any]]:
    """List all workspace branches with their manifest + status."""
    return WorkspaceStore(store).list_workspaces()


def tool_get_workspace_status(store: GitStore, branch_name: str) -> dict[str, Any]:
    """Return a workspace branch's status.json + manifest."""
    return WorkspaceStore(store).get_status(branch_name)


def tool_close_workspace(store: GitStore, branch_name: str) -> dict[str, Any]:
    """Mark a workspace complete. Does not delete/rename the branch."""
    return WorkspaceStore(store).close(branch_name)
