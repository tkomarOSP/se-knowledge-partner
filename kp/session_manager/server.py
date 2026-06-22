"""Session Manager MCP Server.

Manages structured interview, checklist, form, and review sessions.
Session state persists to a local JSON file between restarts.

Transport: streamable-http  (POST /mcp)
Port:      8004

Environment variables:
    SESSION_STORE_PATH  Path to the session persistence JSON file.
                        Default: ~/.knowledge_partner/sessions.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from session_manager.store import SessionStore

_store_path = Path(os.environ.get("SESSION_STORE_PATH", Path.home() / ".knowledge_partner" / "sessions.json"))
store = SessionStore(persist_path=_store_path)

mcp = FastMCP(
    "Session Manager",
    host="127.0.0.1",
    port=8004,
    instructions=(
        "Use create_session to start a new interview, checklist, form, or review session. "
        "Each session has a list of steps; use advance_session to answer each step in order. "
        "Use get_session to inspect current state and the next question. "
        "Use close_session when done — the transcript is returned for archiving. "
        "Session types: interview, checklist, form, review."
    ),
)


@mcp.tool()
def create_session(type: str, title: str, steps: list[dict], metadata: Optional[dict] = None) -> dict:
    """Create a new session.

    Each step in ``steps`` must have at least ``key`` (str) and ``prompt`` (str).
    Optional step fields: ``type`` (text|bool|int|float|choice), ``choices`` (list),
    ``required`` (bool).

    Args:
        type: Session type — ``interview``, ``checklist``, ``form``, or ``review``.
        title: Human-readable session title.
        steps: Ordered list of step dicts.
        metadata: Optional key-value metadata attached to the session.
    """
    try:
        session = store.create(type=type, title=title, steps=steps, metadata=metadata)
        first_step = None
        if session.steps:
            s = session.steps[0]
            first_step = {"key": s.key, "prompt": s.prompt, "type": s.type, "choices": s.choices}
        return {
            "sid": session.sid,
            "title": session.title,
            "type": session.type.value,
            "total_steps": len(session.steps),
            "first_step": first_step,
        }
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def get_session(sid: str) -> dict:
    """Return the current state of a session, including the next unanswered step.

    Args:
        sid: Session ID returned by create_session.
    """
    try:
        s = store.get(sid)
        next_step = None
        if s.current_step < len(s.steps):
            ns = s.steps[s.current_step]
            next_step = {"key": ns.key, "prompt": ns.prompt, "type": ns.type, "choices": ns.choices}
        return {
            "sid": s.sid,
            "title": s.title,
            "type": s.type.value,
            "status": s.status.value,
            "progress": f"{s.current_step}/{len(s.steps)}",
            "answers": s.answers,
            "next_step": next_step,
        }
    except KeyError as exc:
        return {"error": str(exc)}


@mcp.tool()
def advance_session(sid: str, answer: Any) -> dict:
    """Record an answer for the current step and return the next step.

    Args:
        sid: Session ID.
        answer: Answer value for the current step (type depends on step type).
    """
    return store.advance(sid, answer)


@mcp.tool()
def list_sessions(status_filter: Optional[str] = None) -> list[dict]:
    """List all sessions, optionally filtered by status.

    Args:
        status_filter: ``active``, ``completed``, or ``abandoned``.
    """
    return store.list_sessions(status_filter=status_filter)


@mcp.tool()
def close_session(sid: str) -> dict:
    """Mark a session as completed and return the full transcript.

    Args:
        sid: Session ID to close.
    """
    try:
        session = store.close(sid)
        return {
            "sid": session.sid,
            "title": session.title,
            "status": session.status.value,
            "answers": session.answers,
            "transcript": session.transcript,
        }
    except KeyError as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    print(f"Session Manager MCP — store: {_store_path}")
    mcp.run(transport="streamable-http")
