"""Maps artifact type strings to Pydantic artifact classes."""

from __future__ import annotations

from artifact_repo.types.base import BaseArtifact
from artifact_repo.types.common import (
    ArcadiaFabricArtifact,
    DecisionArtifact,
    HtmlArtifact,
    JsonArtifact,
    LessonLearnedArtifact,
    LogBookArtifact,
    ObservationArtifact,
    PromptArtifact,
    PromptDefArtifact,
    RoutineDefArtifact,
    SessionSummaryArtifact,
    TableArtifact,
    TextArtifact,
    YamlArtifact,
)

ARTIFACT_TYPE_REGISTRY: dict[str, type[BaseArtifact]] = {
    "table": TableArtifact,
    "yaml": YamlArtifact,
    "text": TextArtifact,
    "html": HtmlArtifact,
    "arcadia_fabric": ArcadiaFabricArtifact,
    "session_summary": SessionSummaryArtifact,
    "prompt_def": PromptDefArtifact,
    "prompt": PromptArtifact,
    "observation": ObservationArtifact,
    "decision": DecisionArtifact,
    "lesson_learned": LessonLearnedArtifact,
    "log_book": LogBookArtifact,
    "routine_def": RoutineDefArtifact,
    "json": JsonArtifact,
}


def get_artifact_class(type_str: str) -> type[BaseArtifact]:
    """Return the Pydantic class for the given type string, falling back to JsonArtifact."""
    return ARTIFACT_TYPE_REGISTRY.get(type_str, JsonArtifact)


def register_artifact_type(type_str: str, cls: type[BaseArtifact]) -> None:
    """Register a new artifact type at runtime."""
    ARTIFACT_TYPE_REGISTRY[type_str] = cls


def list_registered_types() -> list[str]:
    return sorted(ARTIFACT_TYPE_REGISTRY.keys())
