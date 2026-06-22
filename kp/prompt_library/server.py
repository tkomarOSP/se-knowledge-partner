"""Prompt Library MCP Server.

Manages Jinja2 prompt_def templates stored in a GitHub repository.

Transport: streamable-http  (POST /mcp)
Port:      8003

Session workflow:
    1. clone_prompt_library(remote_url, pat)  — clone library repo, return session_id
    2. browse_prompts / get_prompt / render_prompt / import_prompt
    3. cleanup_session(session_id)            — delete temp clone

Environment variables:
    KP_PROMPT_SESSION_BASE  Base directory for session clones.
                            Default: $TMPDIR/kp_prompt_library
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from prompt_library.store import PromptStore

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_SESSION_BASE = Path(
    os.environ.get(
        "KP_PROMPT_SESSION_BASE",
        str(Path(tempfile.gettempdir()) / "kp_prompt_library"),
    )
)
_sessions: dict[str, PromptStore] = {}


def _inject_pat(url: str, pat: str) -> str:
    scheme, rest = url.split("://", 1)
    return f"{scheme}://oauth2:{pat}@{rest}"


def _scrub_pat(text: str, pat: str) -> str:
    return text.replace(pat, "***") if pat and pat in text else text


def _get_session(session_id: str) -> PromptStore:
    if session_id not in _sessions:
        raise ValueError(f"Unknown session_id '{session_id}'. Call clone_prompt_library first.")
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Prompt Library",
    host="127.0.0.1",
    port=8003,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "prompts.innovatingwithcapella.com",
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
        ],
    ),
    instructions=(
        "Call clone_prompt_library first with a GitHub repo URL and PAT to start a session. "
        "Use browse_prompts to discover available prompt_def templates. "
        "Use get_prompt to inspect a template's required variables. "
        "Use render_prompt to produce a filled-in prompt string. "
        "Use import_prompt to get a prompt_def's JSON for storing in the artifact repo. "
        "Call cleanup_session when done to release server resources."
    ),
)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

@mcp.tool()
def clone_prompt_library(remote_url: str, pat: str, branch: str = "main") -> dict:
    """Clone a GitHub prompt library repository and start a session.

    Returns a session_id required by all subsequent tools.

    Args:
        remote_url: HTTPS URL of the GitHub prompt library repo
        pat: GitHub Personal Access Token with repo read access
        branch: Branch to clone (default: main)
    """
    session_id = uuid.uuid4().hex
    session_dir = _SESSION_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    auth_url = _inject_pat(remote_url, pat)
    result = subprocess.run(
        ["git", "clone", "--branch", branch, auth_url, str(session_dir)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        shutil.rmtree(session_dir, ignore_errors=True)
        return {"error": _scrub_pat(result.stderr.strip(), pat)}

    store = PromptStore(session_dir)
    _sessions[session_id] = store

    return {
        "session_id": session_id,
        "branch": branch,
        "message": f"Cloned {remote_url} — use session_id for all subsequent calls.",
    }


@mcp.tool()
def cleanup_session(session_id: str) -> dict:
    """Delete the session's local clone and release server resources.

    Args:
        session_id: The session ID returned by clone_prompt_library.
    """
    store = _sessions.pop(session_id, None)
    if store:
        shutil.rmtree(store.path, ignore_errors=True)
        return {"status": "cleaned up", "session_id": session_id}
    return {"status": "not found", "session_id": session_id}


# ---------------------------------------------------------------------------
# Prompt tools
# ---------------------------------------------------------------------------

@mcp.tool()
def browse_prompts(session_id: str, tag_filter: Optional[str] = None) -> list[dict]:
    """List all prompt_def templates in the library, optionally filtered by tag.

    Args:
        session_id: Session ID from clone_prompt_library.
        tag_filter: If provided, return only prompts with this tag.
    """
    return _get_session(session_id).list_prompts(tag_filter=tag_filter)


@mcp.tool()
def get_prompt(session_id: str, name: str) -> dict:
    """Return a prompt_def spec including template string and required vars.

    Args:
        session_id: Session ID from clone_prompt_library.
        name: Prompt name.
    """
    try:
        return _get_session(session_id).get_prompt(name)
    except KeyError as exc:
        return {"error": str(exc)}


@mcp.tool()
def render_prompt(session_id: str, name: str, vars: dict) -> dict:
    """Render a prompt_def template with the given variable values.

    Returns ``{"rendered": str}`` on success or ``{"error": str}`` on failure.

    Args:
        session_id: Session ID from clone_prompt_library.
        name: Prompt name.
        vars: Dict of variable name → value to substitute.
    """
    try:
        rendered = _get_session(session_id).render_prompt(name, vars)
        return {"rendered": rendered, "prompt_name": name}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def import_prompt(session_id: str, name: str) -> dict:
    """Return a prompt_def's serialized JSON for storing in the artifact repo.

    The returned ``content_str`` can be passed directly to
    ``write_artifact(type="prompt_def", content_str=...)`` to cache the
    template locally in the project's artifact repo.

    Args:
        session_id: Session ID from clone_prompt_library.
        name: Prompt name to import.
    """
    try:
        spec = _get_session(session_id).get_prompt(name)
        import json
        return {"name": name, "content_str": json.dumps(spec, indent=2)}
    except KeyError as exc:
        return {"error": str(exc)}


@mcp.tool()
def save_prompt(session_id: str, spec: dict) -> dict:
    """Create or update a prompt_def template in the library clone.

    The spec must include ``name``, ``template``, and ``vars``.
    Optional: ``defaults`` (dict), ``tags`` (list), ``description`` (str).

    Note: changes are local to the session clone. Push manually if needed.

    Args:
        session_id: Session ID from clone_prompt_library.
        spec: Prompt specification dict.
    """
    try:
        _get_session(session_id).save_prompt(spec)
        return {"status": "saved", "name": spec.get("name")}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def delete_prompt(session_id: str, name: str) -> dict:
    """Delete a prompt_def template from the library clone.

    Args:
        session_id: Session ID from clone_prompt_library.
        name: Prompt name to delete.
    """
    try:
        _get_session(session_id).delete_prompt(name)
        return {"status": "deleted", "name": name}
    except KeyError as exc:
        return {"error": str(exc)}


@mcp.tool()
def search_prompts(session_id: str, query: str) -> list[dict]:
    """Search prompt_def templates by name, tags, or template content.

    Args:
        session_id: Session ID from clone_prompt_library.
        query: Case-insensitive substring to search for.
    """
    return _get_session(session_id).search_prompts(query)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Prompt Library MCP — session base: {_SESSION_BASE}")
    mcp.run(transport="streamable-http")
