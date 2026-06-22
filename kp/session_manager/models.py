"""Pydantic models for session state."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionType(str, Enum):
    interview = "interview"
    checklist = "checklist"
    form = "form"
    review = "review"


class SessionStatus(str, Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class SessionStep(BaseModel):
    key: str
    prompt: str
    type: str = "text"          # text | bool | int | float | choice
    choices: list[str] = Field(default_factory=list)
    required: bool = True
    answer: Optional[Any] = None
    answered_at: Optional[datetime] = None


class Session(BaseModel):
    sid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: SessionType
    title: str
    steps: list[SessionStep] = Field(default_factory=list)
    current_step: int = 0
    status: SessionStatus = SessionStatus.active
    answers: dict[str, Any] = Field(default_factory=dict)
    transcript: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
