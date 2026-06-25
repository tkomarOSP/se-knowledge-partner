"""Base Pydantic models for all artifact types.

Ported from knowledge_repo/types/base.py as part of the knowledge_repo rework —
the general typed-artifact system now lives here, scoped to workspace branches.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactMetadata(BaseModel):
    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    type: str
    package_name: str
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    tags: list[str] = Field(default_factory=list)
    source_tool: Optional[str] = None
    lineage: list[str] = Field(default_factory=list)  # parent artifact_ids


class BaseArtifact(BaseModel):
    metadata: ArtifactMetadata
    content: Any

    def content_extension(self) -> str:
        return "json"

    def serialize_content(self) -> str:
        return json.dumps(self.content, indent=2, ensure_ascii=False, default=str)

    @classmethod
    def deserialize_content(cls, raw: str) -> Any:
        return json.loads(raw)
