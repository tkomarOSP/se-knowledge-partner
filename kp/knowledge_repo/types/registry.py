"""Maps artifact type strings to Pydantic artifact classes.

NOTE: as of the knowledge_repo indexed-entry rework, knowledge_repo only owns the
4 Knowledge-layer types below. The other 9 types (table, yaml, text, html,
arcadia_fabric, session_summary, prompt_def, prompt, json) have moved to
workspace_manager — they are routine inputs/outputs, persisted inside workspace
branches, not long-term knowledge artifacts. ``log_book`` is no longer a stored
type at all: it is now an assembled view over observation/decision/lesson_learned
entries (see IndexedEntryStore.render_log_book / tool_render_log_book).
"""

from __future__ import annotations

from knowledge_repo.types.base import BaseArtifact
from knowledge_repo.types.common import (
    DecisionArtifact,
    JsonArtifact,
    LessonLearnedArtifact,
    ObservationArtifact,
    RoutineDefArtifact,
)

ARTIFACT_TYPE_REGISTRY: dict[str, type[BaseArtifact]] = {
    "observation": ObservationArtifact,
    "decision": DecisionArtifact,
    "lesson_learned": LessonLearnedArtifact,
    "routine_def": RoutineDefArtifact,
}


def get_artifact_class(type_str: str) -> type[BaseArtifact]:
    """Return the Pydantic class for the given type string, falling back to JsonArtifact."""
    return ARTIFACT_TYPE_REGISTRY.get(type_str, JsonArtifact)


def register_artifact_type(type_str: str, cls: type[BaseArtifact]) -> None:
    """Register a new artifact type at runtime."""
    ARTIFACT_TYPE_REGISTRY[type_str] = cls


def list_registered_types() -> list[str]:
    return sorted(ARTIFACT_TYPE_REGISTRY.keys())
