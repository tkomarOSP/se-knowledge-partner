"""In-memory session store with optional JSON persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from session_manager.models import Session, SessionStatus, SessionStep, SessionType


class SessionStore:
    """Manages active sessions in memory, persisted to a JSON file on disk."""

    def __init__(self, persist_path: Optional[Path] = None):
        self._sessions: dict[str, Session] = {}
        self._persist_path = persist_path
        if persist_path and persist_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {sid: s.model_dump(mode="json") for sid, s in self._sessions.items()}
        self._persist_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _load(self) -> None:
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for sid, data in raw.items():
                self._sessions[sid] = Session.model_validate(data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create(self, type: str, title: str, steps: list[dict[str, Any]], metadata: dict | None = None) -> Session:
        session = Session(
            type=SessionType(type),
            title=title,
            steps=[SessionStep(**s) for s in steps],
            metadata=metadata or {},
        )
        self._sessions[session.sid] = session
        self._save()
        return session

    def get(self, sid: str) -> Session:
        if sid not in self._sessions:
            raise KeyError(f"Session '{sid}' not found.")
        return self._sessions[sid]

    def list_sessions(self, status_filter: Optional[str] = None) -> list[dict[str, Any]]:
        results = []
        for s in self._sessions.values():
            if status_filter and s.status.value != status_filter:
                continue
            results.append({
                "sid": s.sid,
                "type": s.type.value,
                "title": s.title,
                "status": s.status.value,
                "current_step": s.current_step,
                "total_steps": len(s.steps),
                "created_at": s.created_at.isoformat(),
            })
        return sorted(results, key=lambda x: x["created_at"], reverse=True)

    def advance(self, sid: str, answer: Any) -> dict[str, Any]:
        """Record an answer for the current step and advance to the next."""
        session = self.get(sid)
        if session.status != SessionStatus.active:
            return {"error": f"Session '{sid}' is {session.status.value}, not active."}
        if session.current_step >= len(session.steps):
            return {"error": "Session has no more steps."}

        step = session.steps[session.current_step]
        step.answer = answer
        step.answered_at = datetime.now(timezone.utc)
        session.answers[step.key] = answer
        session.transcript.append({
            "step": step.key,
            "prompt": step.prompt,
            "answer": str(answer),
        })
        session.current_step += 1
        session.updated_at = datetime.now(timezone.utc)

        if session.current_step >= len(session.steps):
            session.status = SessionStatus.completed

        self._save()

        next_step = None
        if session.current_step < len(session.steps):
            ns = session.steps[session.current_step]
            next_step = {"key": ns.key, "prompt": ns.prompt, "type": ns.type, "choices": ns.choices}

        return {
            "sid": sid,
            "answered_step": step.key,
            "status": session.status.value,
            "next_step": next_step,
            "progress": f"{session.current_step}/{len(session.steps)}",
        }

    def close(self, sid: str) -> Session:
        session = self.get(sid)
        session.status = SessionStatus.completed
        session.updated_at = datetime.now(timezone.utc)
        self._save()
        return session

    def abandon(self, sid: str) -> None:
        session = self.get(sid)
        session.status = SessionStatus.abandoned
        session.updated_at = datetime.now(timezone.utc)
        self._save()
