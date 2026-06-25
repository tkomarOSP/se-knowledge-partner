"""Concrete artifact type definitions for the 4 Knowledge-layer types.

The other 9 types (table, yaml, text, html, arcadia_fabric, session_summary,
prompt_def, prompt, json) have moved to workspace_manager/types/common.py as
part of the knowledge_repo rework — they are routine inputs/outputs, not
long-term knowledge artifacts.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from knowledge_repo.types.base import BaseArtifact


# ---------------------------------------------------------------------------
# Knowledge types: Observation, Decision, Lesson Learned
# ---------------------------------------------------------------------------

class ObservationContent(BaseModel):
    text: str
    context: str = ""
    evidence: list[str] = Field(default_factory=list)  # artifact_ids supporting this observation
    significance: str = "medium"  # "high", "medium", "low"
    tags: list[str] = Field(default_factory=list)


class ObservationArtifact(BaseArtifact):
    content: ObservationContent

    def content_extension(self) -> str:
        return "json"

    def serialize_content(self) -> str:
        return self.content.model_dump_json(indent=2)

    @classmethod
    def deserialize_content(cls, raw: str) -> ObservationContent:
        return ObservationContent.model_validate_json(raw)


class DecisionContent(BaseModel):
    title: str
    status: str = "proposed"  # "proposed", "accepted", "deprecated", "superseded"
    context: str = ""
    decision: str = ""
    rationale: str = ""
    alternatives: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    related_artifacts: list[str] = Field(default_factory=list)  # artifact_ids


class DecisionArtifact(BaseArtifact):
    content: DecisionContent

    def content_extension(self) -> str:
        return "json"

    def serialize_content(self) -> str:
        return self.content.model_dump_json(indent=2)

    @classmethod
    def deserialize_content(cls, raw: str) -> DecisionContent:
        return DecisionContent.model_validate_json(raw)


class LessonLearnedContent(BaseModel):
    title: str
    what_happened: str = ""
    what_worked: list[str] = Field(default_factory=list)
    what_didnt_work: list[str] = Field(default_factory=list)
    recommendation: str = ""
    phase: str = ""  # project phase or activity where this occurred
    tags: list[str] = Field(default_factory=list)


class LessonLearnedArtifact(BaseArtifact):
    content: LessonLearnedContent

    def content_extension(self) -> str:
        return "json"

    def serialize_content(self) -> str:
        return self.content.model_dump_json(indent=2)

    @classmethod
    def deserialize_content(cls, raw: str) -> LessonLearnedContent:
        return LessonLearnedContent.model_validate_json(raw)


# ---------------------------------------------------------------------------
# Routine definition (declarative KP execution contract)
# ---------------------------------------------------------------------------

class RoutineDefArtifact(BaseArtifact):
    """Declarative YAML artifact defining a replayable KP engineering routine.

    Content is a raw YAML string conforming to the routine_def schema (top-level
    key 'routine_def' with id, name, version, prompt_template at minimum).
    The KP reads this artifact and executes it at conversation time — no code required.
    Stored as an indexed entry (see IndexedEntryStore), same as the other 3 Knowledge types.
    """
    content: str  # raw YAML string

    def content_extension(self) -> str:
        return "yaml"

    def serialize_content(self) -> str:
        return self.content

    @classmethod
    def deserialize_content(cls, raw: str) -> str:
        import yaml  # noqa: PLC0415 — lazy to avoid top-level dep in non-server contexts
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML: {exc}") from exc
        if not isinstance(parsed, dict) or "routine_def" not in parsed:
            raise ValueError("routine_def YAML must have a top-level 'routine_def' key")
        rd = parsed["routine_def"]
        required = {"id", "name", "version", "prompt_template"}
        missing = required - rd.keys()
        if missing:
            raise ValueError(f"routine_def missing required fields: {sorted(missing)}")
        return raw


# ---------------------------------------------------------------------------
# Generic JSON fallback (used by ARTIFACT_TYPE_REGISTRY.get_artifact_class default)
# ---------------------------------------------------------------------------

class JsonArtifact(BaseArtifact):
    content: Optional[object] = None

    def content_extension(self) -> str:
        return "json"
