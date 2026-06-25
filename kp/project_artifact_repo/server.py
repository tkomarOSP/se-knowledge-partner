"""Project Artifact Repository MCP Server.

The first destination-layer MCP for promoted workspace outputs (Layer 3 —
FMEA, Pugh matrices, requirements impact analyses, trade studies). Deliberately
minimal: reuses workspace_manager's typed-artifact store/types directly rather
than re-porting them a third time (see kp/workspace_manager/store/git_store.py,
types/registry.py) — this server only adds its own session lifecycle and a
write_artifact tool, since that is all a destination layer needs.

HARD REQUIREMENT: never point this at the Capella model repo. Mixing artifact
writes into a remote Capella also commits to causes fast-forward conflicts —
this must be its own plain git repo, always.

Transport: streamable-http  (POST /mcp)
Port:      8006

Environment variables:
    KP_PROJECT_REPO_SESSION_BASE  Base directory for session clones.
                                   Default: $TMPDIR/kp_project_artifact_repo
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
from workspace_manager.types.registry import list_registered_types

_SESSION_BASE = Path(
    os.environ.get(
        "KP_PROJECT_REPO_SESSION_BASE",
        str(Path(tempfile.gettempdir()) / "kp_project_artifact_repo"),
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
        raise ValueError(f"Unknown session_id '{session_id}'. Call create_session first.")
    return _sessions[session_id]


mcp = FastMCP(
    "Project Artifact Repository",
    host="127.0.0.1",
    port=8006,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
    ),
    instructions=(
        "Call create_session first with a git repo URL and PAT to start a session. "
        "NEVER point this at the Capella model repo — it must be its own plain git "
        "repo, separate from anything capella-fabric manages, to avoid fast-forward "
        "conflicts. "
        "This is the first destination-layer MCP for promoted workspace outputs "
        "(Layer 3 — FMEA, Pugh, trade studies, requirements impact analyses). "
        "Typical promotion flow: workspace_manager.read_workspace_artifact(branch, "
        "output_name) to fetch content, then write_artifact here to place it. "
        "Use browse_artifacts/read_artifact/search_artifacts to discover what's "
        "already here. Call push_artifacts to sync commits back to the remote. "
        "Call cleanup_session when done. "
        f"Registered types: {', '.join(list_registered_types())}."
    ),
)


@mcp.tool()
def create_session(remote_url: str, pat: str, branch: str = "main") -> dict:
    """Clone a git repository and start a session.

    HARD REQUIREMENT: never point this at the Capella model repo.

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

    subprocess.run(["git", "-C", str(session_dir), "config", "user.name", "KP Project Artifact Repo"], capture_output=True)
    subprocess.run(["git", "-C", str(session_dir), "config", "user.email", "kp@project-artifact-repo"], capture_output=True)

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
    """Write (create or overwrite) an artifact — the promotion landing point.

    type must be one of: table, yaml, text, html, arcadia_fabric, session_summary,
    prompt_def, prompt, json — same registry as workspace_manager, since promoted
    content is already one of these typed artifacts.
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
    """Push all locally committed artifacts to the remote repository."""
    return tool_push_artifacts(_get_session(session_id))


if __name__ == "__main__":
    print(f"Project Artifact Repository MCP — session base: {_SESSION_BASE}")
    mcp.run(transport="streamable-http")
