"""Maps artifact type strings to Pydantic artifact classes.

These are the 9 types ported out of knowledge_repo as part of its indexed-entry
rework — table, yaml, text, html, arcadia_fabric, session_summary, prompt_def,
prompt, json. They are routine inputs/outputs, persisted inside workspace
branches managed by this package.
"""

from __future__ import annotations

from workspace_manager.types.base import BaseArtifact
from workspace_manager.types.common import (
    ArcadiaFabricArtifact,
    HtmlArtifact,
    JsonArtifact,
    PromptArtifact,
    PromptDefArtifact,
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
