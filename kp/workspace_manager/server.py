"""Workspace Manager MCP Server.

Owns the general typed-artifact system (table, yaml, text, html, arcadia_fabric,
session_summary, prompt_def, prompt, json) — these are routine inputs/outputs,
persisted both on the session's normal branch and inside per-routine-execution
workspace branches. Also owns workspace lifecycle: create/write/list/status/close.

Promotion is intentionally NOT implemented here — see read_workspace_artifact;
the destination (e.g. a project_artifact_repo MCP) owns the logic for placing
content into its own layer. This server, and project_artifact_repo, must never
be pointed at the Capella model repo — that caused real fast-forward conflicts
when both Capella and artifact writes targeted the same remote.

Transport: streamable-http  (POST /mcp)
Port:      8005

Environment variables:
    KP_WORKSPACE_SESSION_BASE  Base directory for session clones.
                                Default: $TMPDIR/kp_workspace_manager
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from workspace_manager.store.git_store import GitStore
from workspace_manager.tools.crud_tools import (
    tool_delete_artifact,
    tool_get_artifact_versions,
    tool_list_artifacts,
    tool_list_packages,
    tool_push_artifacts,
    tool_read_artifact,
    tool_search_artifacts,
    tool_write_artifact,
)
from workspace_manager.tools.workspace_tools import (
    tool_close_workspace,
    tool_create_workspace,
    tool_get_workspace_status,
    tool_list_workspaces,
    tool_read_workspace_artifact,
    tool_write_workspace_artifact,
)
from workspace_manager.types.registry import list_registered_types

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_SESSION_BASE = Path(
    os.environ.get(
        "KP_WORKSPACE_SESSION_BASE",
        str(Path(tempfile.gettempdir()) / "kp_workspace_manager"),
    )
)
_sessions: dict[str, GitStore] = {}


def _inject_pat(url: str, pat: str) -> str:
    scheme, rest = url.split("://", 1)
    return f"{scheme}://oauth2:{pat}@{rest}"


def _is_gitlab_host(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return "gitlab" in hostname or hostname == "code.siemens.com"


def _scrub_pat(text: str, pat: str) -> str:
    return text.replace(pat, "***") if pat and pat in text else text


def _get_session(session_id: str) -> GitStore:
    if session_id not in _sessions:
        raise ValueError(f"Unknown session_id '{session_id}'. Call create_workspace_session first.")
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Workspace Manager",
    host="127.0.0.1",
    port=8005,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
    ),
    instructions=(
        "Call create_workspace_session first with a git repo URL and PAT to start a session. "
        "NEVER point this at the Capella model repo — mixing artifact writes into a remote "
        "Capella also commits to causes fast-forward conflicts. "
        "This server owns the general typed-artifact system: table, yaml, text, html, "
        "arcadia_fabric, session_summary, prompt_def, prompt, json — these are routine "
        "inputs/outputs. Use write_artifact/read_artifact/browse_artifacts/search_artifacts "
        "for artifacts on the session's current branch (usually main). "
        "Use create_workspace to start a new per-routine-execution branch, "
        "write_workspace_artifact to record a typed output into it (committed immediately), "
        "list_workspaces/get_workspace_status to check progress, and close_workspace when done "
        "(this only flips status to 'complete' — it never deletes or renames the branch, so "
        "work always survives). "
        "There is no promote tool here — read_workspace_artifact fetches an output's content "
        "so a destination-layer MCP (e.g. project_artifact_repo) can place it in its own layer. "
        "Call push_artifacts to sync commits back to the remote. "
        "Call cleanup_session when done to free server resources. "
        f"Registered types: {', '.join(list_registered_types())}."
    ),
)


# ---------------------------------------------------------------------------
# Session lifecycle tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_workspace_session(remote_url: str, pat: str, branch: str = "main") -> dict:
    """Clone a git repository (GitHub or GitLab) and start a session.

    Call this first. NEVER point this at the Capella model repo.

    Args:
        remote_url: HTTPS URL of the repo.
        pat: Personal Access Token with repo read/write access.
        branch: Branch to clone (default: main).
    """
    session_id = uuid.uuid4().hex
    session_dir = _SESSION_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    if _is_gitlab_host(remote_url):
        clone_cmd = [
            "git", "clone", "--branch", branch,
            "-c", f"http.extraHeader=PRIVATE-TOKEN: {pat}",
            remote_url, str(session_dir),
        ]
    else:
        clone_cmd = ["git", "clone", "--branch", branch, _inject_pat(remote_url, pat), str(session_dir)]

    result = subprocess.run(clone_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.rmtree(session_dir, ignore_errors=True)
        return {"error": _scrub_pat(result.stderr.strip(), pat)}

    subprocess.run(["git", "-C", str(session_dir), "config", "user.name", "KP Workspace Manager"], capture_output=True)
    subprocess.run(["git", "-C", str(session_dir), "config", "user.email", "kp@workspace"], capture_output=True)

    if _is_gitlab_host(remote_url):
        subprocess.run(
            ["git", "-C", str(session_dir), "config", "http.extraHeader", f"PRIVATE-TOKEN: {pat}"],
            capture_output=True,
        )

    store = GitStore(session_dir)
    _sessions[session_id] = store

    return {
        "session_id": session_id,
        "branch": store.branch,
        "message": f"Cloned {remote_url} — use session_id for all subsequent calls.",
    }


@mcp.tool()
def cleanup_session(session_id: str) -> dict:
    """Delete the session's local clone and release server resources."""
    store = _sessions.pop(session_id, None)
    if store:
        shutil.rmtree(store.root, ignore_errors=True)
        return {"status": "cleaned up", "session_id": session_id}
    return {"status": "not found", "session_id": session_id}


# ---------------------------------------------------------------------------
# General typed-artifact CRUD tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_artifact_packages(session_id: str) -> list[str]:
    """Return the names of all packages in the repository."""
    return tool_list_packages(_get_session(session_id))


@mcp.tool()
def browse_artifacts(
    session_id: str,
    package: str,
    type_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Browse artifact metadata in a package."""
    return tool_list_artifacts(_get_session(session_id), package, type_filter, name_filter, limit)


@mcp.tool()
def read_artifact(session_id: str, package: str, artifact_id: str) -> dict:
    """Read a single artifact by ID. Returns {metadata, content_str, type}."""
    return tool_read_artifact(_get_session(session_id), package, artifact_id)


@mcp.tool()
def write_artifact(
    session_id: str,
    package: str,
    type: str,
    name: str,
    content_str: str,
    tags: Optional[list[str]] = None,
    source_tool: Optional[str] = None,
    lineage: Optional[list[str]] = None,
    artifact_id: Optional[str] = None,
) -> dict:
    """Write (create or overwrite) an artifact on the session's current branch.

    type must be one of: table, yaml, text, html, arcadia_fabric, session_summary,
    prompt_def, prompt, json.
    """
    return tool_write_artifact(
        _get_session(session_id), package, type, name, content_str, tags, source_tool, lineage, artifact_id
    )


@mcp.tool()
def delete_artifact(session_id: str, package: str, artifact_id: str) -> dict:
    """Delete an artifact from the repository."""
    return tool_delete_artifact(_get_session(session_id), package, artifact_id)


@mcp.tool()
def get_artifact_versions(session_id: str, package: str, artifact_id: str) -> list[dict]:
    """Return git commit history for an artifact."""
    return tool_get_artifact_versions(_get_session(session_id), package, artifact_id)


@mcp.tool()
def search_artifacts(session_id: str, package: str, query: str, type_filter: Optional[str] = None) -> list[dict]:
    """Full-text search across artifact names, tags, and content files."""
    return tool_search_artifacts(_get_session(session_id), package, query, type_filter)


@mcp.tool()
def push_artifacts(session_id: str) -> dict:
    """Push all locally committed artifacts/workspaces to the remote repository."""
    return tool_push_artifacts(_get_session(session_id))


# ---------------------------------------------------------------------------
# Workspace lifecycle tools
# ---------------------------------------------------------------------------

@mcp.tool()
def create_workspace(session_id: str, routine_id: str, engineer: Optional[str] = None) -> dict:
    """Create a new workspace branch (workspace/{routine_id}-{date}) for a routine execution.

    Args:
        session_id: Session ID from create_workspace_session.
        routine_id: The routine_def's id — becomes part of the branch name.
        engineer: Optional engineer/agent name attributed to this execution.
    """
    return tool_create_workspace(_get_session(session_id), routine_id, engineer)


@mcp.tool()
def write_workspace_artifact(
    session_id: str,
    branch_name: str,
    package: str,
    type: str,
    name: str,
    content_str: str,
    tags: Optional[list[str]] = None,
) -> dict:
    """Write a typed artifact into a workspace branch, committed immediately.

    Args:
        session_id: Session ID from create_workspace_session.
        branch_name: The workspace branch (from create_workspace's response).
        package: Package name within the workspace.
        type: One of table/yaml/text/html/arcadia_fabric/session_summary/prompt_def/prompt/json.
        name: Human-readable name for this output.
        content_str: Serialized content (format depends on type).
        tags: Optional tag list.
    """
    return tool_write_workspace_artifact(_get_session(session_id), branch_name, package, type, name, content_str, tags)


@mcp.tool()
def read_workspace_artifact(session_id: str, branch_name: str, output_name: str) -> dict:
    """Read one workspace output's content via `git show` — the only promotion primitive
    this server provides. A destination-layer MCP (e.g. project_artifact_repo) takes this
    content and places it in its own layer.

    Args:
        session_id: Session ID from create_workspace_session.
        branch_name: The workspace branch.
        output_name: The output's name (as passed to write_workspace_artifact).
    """
    return tool_read_workspace_artifact(_get_session(session_id), branch_name, output_name)


@mcp.tool()
def list_workspaces(session_id: str) -> list[dict]:
    """List all workspace branches with their manifest + status."""
    return tool_list_workspaces(_get_session(session_id))


@mcp.tool()
def get_workspace_status(session_id: str, branch_name: str) -> dict:
    """Return a workspace branch's status + manifest (outputs written so far)."""
    return tool_get_workspace_status(_get_session(session_id), branch_name)


@mcp.tool()
def close_workspace(session_id: str, branch_name: str) -> dict:
    """Mark a workspace complete. Does NOT delete or rename the branch — it is left
    untouched on the remote indefinitely so the work always remains accessible."""
    return tool_close_workspace(_get_session(session_id), branch_name)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Workspace Manager MCP — session base: {_SESSION_BASE}")
    mcp.run(transport="streamable-http")
