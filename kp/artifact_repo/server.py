"""Artifact Repository MCP Server.

Exposes CRUD operations for Pydantic-typed, git-backed artifacts.

Transport: streamable-http  (POST /mcp)
Port:      8002

Session workflow:
    1. connect_repo(remote_url, pat)       — clone GitHub repo, return session_id
    2. list / read / write / search        — all take session_id as first arg
    3. push_repo_artifacts(session_id)     — push commits back to GitHub
    4. cleanup_repo_session(session_id)    — delete temp clone, free resources

Environment variables:
    KP_REPO_SESSION_BASE  Base directory for session clones.
                          Default: $TMPDIR/kp_artifact_repo
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

from artifact_repo.store.git_store import GitStore
from artifact_repo.tools.crud_tools import (
    tool_add_log_entry,
    tool_delete_repo_artifact,
    tool_get_repo_artifact_versions,
    tool_list_repo_artifacts,
    tool_list_repo_packages,
    tool_list_routines,
    tool_push_repo_artifacts,
    tool_read_repo_artifact,
    tool_render_prompt,
    tool_render_routine_prompt,
    tool_search_repo_artifacts,
    tool_validate_routine_def,
    tool_write_repo_artifact,
)
from artifact_repo.types.registry import list_registered_types

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_SESSION_BASE = Path(
    os.environ.get(
        "KP_REPO_SESSION_BASE",
        str(Path(tempfile.gettempdir()) / "kp_artifact_repo"),
    )
)
_sessions: dict[str, GitStore] = {}

# Optional: base URL of the KP Artifact Viewer (e.g. https://artifacts.innovatingwithcapella.com)
# When set, write_artifact / add_log_entry / list_routines include a viewer_url in their response.
_VIEWER_BASE_URL = os.environ.get("KP_VIEWER_BASE_URL", "").rstrip("/")


def _inject_pat(url: str, pat: str) -> str:
    """Embed PAT into an HTTPS URL: https://... → https://oauth2:{pat}@..."""
    scheme, rest = url.split("://", 1)
    return f"{scheme}://oauth2:{pat}@{rest}"


def _is_gitlab_host(url: str) -> bool:
    """GitLab instances enforcing SSO (e.g. code.siemens.com) reject PAT-in-URL
    basic auth with a redirect to the SSO login page. They accept the PAT via
    the PRIVATE-TOKEN header instead, so those hosts need different handling."""
    hostname = urlparse(url).hostname or ""
    return "gitlab" in hostname or hostname == "code.siemens.com"


def _scrub_pat(text: str, pat: str) -> str:
    return text.replace(pat, "***") if pat and pat in text else text


def _get_session(session_id: str) -> GitStore:
    if session_id not in _sessions:
        raise ValueError(f"Unknown session_id '{session_id}'. Call connect_repo first.")
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Knowledge Repository",
    host="127.0.0.1",
    port=8002,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "repo.innovatingwithcapella.com",
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
        ],
    ),
    instructions=(
        "Call clone_knowledge_repo first with a GitHub repo URL and PAT to start a session. "
        "All other tools require the session_id returned by clone_knowledge_repo. "
        "Use list_artifact_packages, browse_knowledge_repo, search_artifacts to discover artifacts. "
        "Use read_artifact to get content. "
        "Use write_artifact to store artifacts — content_str format by type: "
        "CSV for 'table', YAML for 'yaml'/'arcadia_fabric'/'routine_def', "
        "Markdown for 'text'/'session_summary'/'log_book', "
        "raw HTML for 'html' (renders as-is in the viewer, not as Markdown — use when "
        "Markdown can't achieve the needed presentation, e.g. complex tables/layout), "
        "JSON for 'observation'/'decision'/'lesson_learned' and others. "
        "Use add_log_entry to append timestamped entries to a log_book artifact. "
        "Use list_routines to discover routine_def artifacts (replayable KP task definitions). "
        "Use validate_routine_def to check a routine_def schema before running it. "
        "Use render_routine_prompt to dry-run a routine_def's prompt_template with Jinja2 "
        "before full execution — catches template errors early. "
        "Call push_artifacts to sync commits back to GitHub. "
        "Call cleanup_session when the activity is complete to free server resources. "
        f"Registered types: {', '.join(list_registered_types())}."
    ),
)


# ---------------------------------------------------------------------------
# Session lifecycle tools
# ---------------------------------------------------------------------------

@mcp.tool()
def clone_knowledge_repo(remote_url: str, pat: str, branch: str = "main") -> dict:
    """Clone a knowledge repository (GitHub or GitLab) and start a session.

    Call this first. Clones the repo to a temporary directory on the server
    so all existing artifacts are available for reading and writing.
    Returns a session_id required by all subsequent tools.
    Call cleanup_session when the activity is complete.

    GitLab hosts (e.g. code.siemens.com) authenticate via the PRIVATE-TOKEN
    header to bypass SSO-redirect-on-basic-auth; GitHub uses PAT-in-URL.

    Args:
        remote_url: HTTPS URL of the repo (e.g. https://github.com/owner/repo
            or https://code.siemens.com/group/repo)
        pat: Personal Access Token with repo read/write access
        branch: Branch to clone (default: main)
    """
    session_id = uuid.uuid4().hex
    session_dir = _SESSION_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    if _is_gitlab_host(remote_url):
        # PRIVATE-TOKEN header auth bypasses GitLab's SSO-redirect-on-basic-auth.
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

    subprocess.run(["git", "-C", str(session_dir), "config", "user.name", "KP Artifact Repo"], capture_output=True)
    subprocess.run(["git", "-C", str(session_dir), "config", "user.email", "kp@repo"], capture_output=True)

    if _is_gitlab_host(remote_url):
        # Persist the header so later pushes (which reuse the clean remote URL) authenticate too.
        subprocess.run(
            ["git", "-C", str(session_dir), "config", "http.extraHeader", f"PRIVATE-TOKEN: {pat}"],
            capture_output=True,
        )

    store = GitStore(session_dir)
    _sessions[session_id] = store

    return {
        "session_id": session_id,
        "branch": store.branch,   # actual branch detected from git (may differ from requested)
        "message": f"Cloned {remote_url} — use session_id for all subsequent calls.",
    }


@mcp.tool()
def cleanup_session(session_id: str) -> dict:
    """Delete the session's local clone and release server resources.

    Call this when the activity is complete (after push_artifacts if needed).
    The session_id will no longer be valid after this call.

    Args:
        session_id: The session ID returned by clone_knowledge_repo.
    """
    store = _sessions.pop(session_id, None)
    if store:
        shutil.rmtree(store.root, ignore_errors=True)
        return {"status": "cleaned up", "session_id": session_id}
    return {"status": "not found", "session_id": session_id}


# ---------------------------------------------------------------------------
# CRUD tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_artifact_packages(session_id: str) -> list[str]:
    """Return the names of all packages in the repository.

    Args:
        session_id: Session ID from clone_knowledge_repo.
    """
    return tool_list_repo_packages(_get_session(session_id))


@mcp.tool()
def browse_knowledge_repo(
    session_id: str,
    package: str,
    type_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Browse artifact metadata in a package.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name to query.
        type_filter: Restrict to this artifact type (e.g. 'observation', 'decision', 'log_book').
        name_filter: Return only artifacts whose name contains this substring.
        limit: Maximum number of results (default 100).
    """
    return tool_list_repo_artifacts(_get_session(session_id), package, type_filter, name_filter, limit)


@mcp.tool()
def read_artifact(session_id: str, package: str, artifact_id: str) -> dict:
    """Read a single artifact by ID.

    Returns a dict with ``metadata`` (dict), ``content_str`` (str), and ``type`` (str).

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name.
        artifact_id: The artifact's UUID.
    """
    return tool_read_repo_artifact(_get_session(session_id), package, artifact_id)


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
    """Write (create or overwrite) an artifact.

    Content format by type:
    - ``table``: CSV text with header row
    - ``yaml`` / ``arcadia_fabric``: raw YAML text
    - ``text`` / ``session_summary``: Markdown text
    - ``json`` / others: JSON string

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name (auto-created if needed).
        type: Artifact type string.
        name: Human-readable name.
        content_str: Serialized content (format depends on type).
        tags: Optional tag list for search/filtering.
        source_tool: Name of the tool that produced this artifact.
        lineage: IDs of parent artifacts this was derived from.
        artifact_id: Provide to overwrite an existing artifact; omit to create new.
    """
    result = tool_write_repo_artifact(
        _get_session(session_id), package, type, name, content_str, tags, source_tool, lineage, artifact_id
    )
    if _VIEWER_BASE_URL and "artifact_id" in result and "error" not in result:
        result["viewer_url"] = f"{_VIEWER_BASE_URL}/{package}/{result['artifact_id']}"
    return result


@mcp.tool()
def delete_artifact(session_id: str, package: str, artifact_id: str) -> dict:
    """Delete an artifact from the repository.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name.
        artifact_id: The artifact's UUID.
    """
    return tool_delete_repo_artifact(_get_session(session_id), package, artifact_id)


@mcp.tool()
def get_artifact_versions(session_id: str, package: str, artifact_id: str) -> list[dict]:
    """Return git commit history for an artifact.

    Each entry has ``commit`` (hash), ``timestamp``, and ``message``.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name.
        artifact_id: The artifact's UUID.
    """
    return tool_get_repo_artifact_versions(_get_session(session_id), package, artifact_id)


@mcp.tool()
def search_artifacts(
    session_id: str,
    package: str,
    query: str,
    type_filter: Optional[str] = None,
) -> list[dict]:
    """Full-text search across artifact names, tags, and content files.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name to search.
        query: Case-insensitive substring to search for.
        type_filter: Restrict results to this artifact type.
    """
    return tool_search_repo_artifacts(_get_session(session_id), package, query, type_filter)


@mcp.tool()
def list_artifact_branches(session_id: str) -> list[str]:
    """List all remote branches in the artifact repository.

    Useful for discovering available branches before cloning a specific one.

    Args:
        session_id: Session ID from clone_knowledge_repo.
    """
    return _get_session(session_id).list_branches()


@mcp.tool()
def create_artifact_branch(
    session_id: str,
    branch_name: str,
    push_upstream: bool = True,
) -> dict:
    """Create a new branch from the current HEAD of the session clone.

    If push_upstream=True (default), the branch is pushed to the remote
    immediately so other sessions can clone it.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        branch_name: Name for the new branch.
        push_upstream: If True, push the new branch to remote origin.
    """
    return _get_session(session_id).create_branch(branch_name, push_upstream)


@mcp.tool()
def add_log_entry(
    session_id: str,
    package: str,
    log_book_id: str,
    text: str,
    entry_type: str = "note",
    artifact_refs: Optional[list[str]] = None,
    author: Optional[str] = None,
) -> dict:
    """Append a timestamped entry to a log_book artifact.

    Use this instead of read+write to avoid Markdown formatting errors.
    Each call appends a dated section to the Markdown file on disk.

    entry_type suggestions: "note", "milestone", "observation", "decision", "issue"

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name.
        log_book_id: artifact_id of the log_book to append to.
        text: Entry body text.
        entry_type: Category label for the section header (default: "note").
        artifact_refs: Optional artifact_ids to cite in this entry.
        author: Optional engineer/agent name to attribute this entry to (appears in the
                entry header). Omit if unknown — older entries have no author.
    """
    result = tool_add_log_entry(_get_session(session_id), package, log_book_id, text, entry_type, artifact_refs, author)
    if _VIEWER_BASE_URL and result.get("status") == "ok":
        result["viewer_url"] = f"{_VIEWER_BASE_URL}/{package}/{log_book_id}"
    return result


@mcp.tool()
def render_prompt(
    session_id: str,
    package: str,
    prompt_name: str,
    variables: Optional[dict] = None,
    save_rendered: bool = False,
) -> dict:
    """Find a prompt_def by name, render it with Jinja2, and optionally save the result.

    Looks for a 'prompt_def' artifact matching prompt_name in the given package.
    Returns the rendered text. If not found locally, call render_prompt on the
    prompt library session instead.

    If save_rendered=True, writes a 'prompt' artifact (type="prompt") to the same
    package with lineage pointing to the prompt_def — for traceability.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name to search for the prompt_def.
        prompt_name: Name of the prompt_def artifact.
        variables: Dict of variable values to substitute into the template.
        save_rendered: If True, save the rendered output as a 'prompt' artifact.
    """
    return tool_render_prompt(_get_session(session_id), package, prompt_name, variables, save_rendered)


@mcp.tool()
def list_routines(
    session_id: str,
    package: Optional[str] = None,
) -> list[dict]:
    """List all routine_def artifacts, optionally filtered to a single package.

    If package is omitted, searches all packages in the repository.
    Returns artifact_id, name, package, version, description, tags, updated_at per routine.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name to restrict the search; omit to search all packages.
    """
    results = tool_list_routines(_get_session(session_id), package)
    if _VIEWER_BASE_URL:
        for r in results:
            r["viewer_url"] = f"{_VIEWER_BASE_URL}/{r['package']}/{r['artifact_id']}"
    return results


@mcp.tool()
def validate_routine_def(
    session_id: str,
    package: str,
    artifact_id: str,
) -> dict:
    """Validate the schema of a routine_def artifact without executing it.

    Checks structural completeness: required fields, variable/resource/output entries.
    Does not check resource accessibility (no credentials required).
    Returns {valid, errors, warnings, passed, summary}. `passed` lists fields/sections
    that validated cleanly — useful to confirm a fix didn't regress something else.
    Unrecognized top-level keys that look like typos of known fields (e.g.
    'pre_flight_checks') surface as warnings with a suggested correction.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name.
        artifact_id: artifact_id of the routine_def to validate.
    """
    return tool_validate_routine_def(_get_session(session_id), package, artifact_id)


@mcp.tool()
def render_routine_prompt(
    session_id: str,
    package: str,
    artifact_id: str,
    variables: Optional[dict] = None,
) -> dict:
    """Dry-run render a routine_def's prompt_template with Jinja2 — template only, NOT execution.

    Catches Jinja2 syntax errors (typos in variable names, unclosed {% if %} blocks)
    before running the routine for real. Does NOT fetch resources, inputs, or Capella
    fabric — the rendered text will be missing anything that depends on those, so do
    not mistake this output for the result of full routine execution.

    Args:
        session_id: Session ID from clone_knowledge_repo.
        package: Package name.
        artifact_id: artifact_id of the routine_def to render.
        variables: Dict of variable values to substitute; merged over each declared
                   variable's 'default'.
    """
    return tool_render_routine_prompt(_get_session(session_id), package, artifact_id, variables)


@mcp.tool()
def push_artifacts(session_id: str) -> dict:
    """Push all locally committed artifacts to the remote GitHub repository.

    Call this before cleanup_session to persist new artifacts to GitHub.

    Args:
        session_id: Session ID from clone_knowledge_repo.
    """
    return tool_push_repo_artifacts(_get_session(session_id))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Artifact Repository MCP — session base: {_SESSION_BASE}")
    mcp.run(transport="streamable-http")
