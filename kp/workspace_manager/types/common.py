"""Concrete artifact type definitions.

Ported from knowledge_repo/types/common.py as part of the knowledge_repo rework.
These 9 types — table, yaml, text, html, arcadia_fabric, session_summary,
prompt_def, prompt, json — are routine inputs/outputs and general engineering
data, persisted inside workspace branches. The 4 Knowledge-layer types
(observation, decision, lesson_learned, routine_def) stay in knowledge_repo.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Optional

from pydantic import BaseModel, Field

from workspace_manager.types.base import BaseArtifact


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------

class TableContent(BaseModel):
    columns: list[str]
    records: list[dict[str, Any]]
    source_file: Optional[str] = None


class TableArtifact(BaseArtifact):
    content: TableContent

    def content_extension(self) -> str:
        return "csv"

    def serialize_content(self) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self.content.columns)
        writer.writeheader()
        writer.writerows(self.content.records)
        return buf.getvalue()

    @classmethod
    def deserialize_content(cls, raw: str) -> TableContent:
        reader = csv.DictReader(io.StringIO(raw))
        records = list(reader)
        columns = reader.fieldnames or (list(records[0].keys()) if records else [])
        return TableContent(columns=list(columns), records=records)


# ---------------------------------------------------------------------------
# YAML / plain text
# ---------------------------------------------------------------------------

class YamlArtifact(BaseArtifact):
    content: str  # raw YAML string

    def content_extension(self) -> str:
        return "yaml"

    def serialize_content(self) -> str:
        return self.content

    @classmethod
    def deserialize_content(cls, raw: str) -> str:
        return raw


class TextArtifact(BaseArtifact):
    content: str  # markdown or plain text

    def content_extension(self) -> str:
        return "md"

    def serialize_content(self) -> str:
        return self.content

    @classmethod
    def deserialize_content(cls, raw: str) -> str:
        return raw


class HtmlArtifact(BaseArtifact):
    content: str  # raw HTML

    def content_extension(self) -> str:
        return "html"

    def serialize_content(self) -> str:
        return self.content

    @classmethod
    def deserialize_content(cls, raw: str) -> str:
        return raw


# ---------------------------------------------------------------------------
# Arcadia / Capella Fabric
# ---------------------------------------------------------------------------

class FabricContent(BaseModel):
    yaml_text: str
    object_count: int = 0
    model_source: Optional[str] = None  # capella repo URL or local path
    targets: list[str] = Field(default_factory=list)


class ArcadiaFabricArtifact(BaseArtifact):
    content: FabricContent

    def content_extension(self) -> str:
        return "yaml"

    def serialize_content(self) -> str:
        return self.content.yaml_text

    @classmethod
    def deserialize_content(cls, raw: str) -> FabricContent:
        # raw is the YAML text; wrap it in the structured model
        return FabricContent(yaml_text=raw)


# ---------------------------------------------------------------------------
# Session summary
# ---------------------------------------------------------------------------

class SessionSummaryContent(BaseModel):
    title: str
    context: str = ""
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    raw_summary: str = ""


class SessionSummaryArtifact(BaseArtifact):
    content: SessionSummaryContent

    def content_extension(self) -> str:
        return "md"

    def serialize_content(self) -> str:
        c = self.content
        lines = [f"# {c.title}", ""]
        if c.context:
            lines += ["## Context", c.context, ""]
        if c.key_points:
            lines += ["## Key Points"] + [f"- {p}" for p in c.key_points] + [""]
        if c.decisions:
            lines += ["## Decisions"] + [f"- {d}" for d in c.decisions] + [""]
        if c.open_questions:
            lines += ["## Open Questions"] + [f"- {q}" for q in c.open_questions] + [""]
        if c.next_steps:
            lines += ["## Next Steps"] + [f"- {s}" for s in c.next_steps] + [""]
        if c.raw_summary:
            lines += ["## Full Summary", c.raw_summary]
        return "\n".join(lines)

    @classmethod
    def deserialize_content(cls, raw: str) -> SessionSummaryContent:
        # Store raw markdown as-is in raw_summary; title extracted from first heading
        title = ""
        for line in raw.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        return SessionSummaryContent(title=title, raw_summary=raw)


# ---------------------------------------------------------------------------
# Generic JSON artifact (fallback for untyped Pydantic content)
# ---------------------------------------------------------------------------

class JsonArtifact(BaseArtifact):
    content: Any

    def content_extension(self) -> str:
        return "json"


# ---------------------------------------------------------------------------
# Prompt definition (Jinja2 template stored in library / project)
# ---------------------------------------------------------------------------

class PromptDefContent(BaseModel):
    template: str
    vars: list[str] = Field(default_factory=list)
    defaults: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    description: str = ""


class PromptDefArtifact(BaseArtifact):
    content: PromptDefContent

    def content_extension(self) -> str:
        return "json"

    def serialize_content(self) -> str:
        return self.content.model_dump_json(indent=2)

    @classmethod
    def deserialize_content(cls, raw: str) -> PromptDefContent:
        return PromptDefContent.model_validate_json(raw)


# ---------------------------------------------------------------------------
# Rendered prompt (result of rendering a prompt_def with specific variables)
# ---------------------------------------------------------------------------

class PromptContent(BaseModel):
    prompt_def_name: str
    variables_used: dict[str, Any] = Field(default_factory=dict)
    rendered_text: str
    source: str = ""  # "local" or "library"


class PromptArtifact(BaseArtifact):
    content: PromptContent

    def content_extension(self) -> str:
        return "md"

    def serialize_content(self) -> str:
        c = self.content
        lines = [
            f"# Prompt: {c.prompt_def_name}",
            "",
            f"**Source:** {c.source or 'local'}",
            "",
        ]
        if c.variables_used:
            lines += ["## Variables Used", ""]
            for k, v in c.variables_used.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")
        lines += ["## Rendered Text", "", c.rendered_text]
        return "\n".join(lines)

    @classmethod
    def deserialize_content(cls, raw: str) -> PromptContent:
        # Parse rendered_text from the Markdown body
        rendered = ""
        in_body = False
        for line in raw.splitlines():
            if line.strip() == "## Rendered Text":
                in_body = True
                continue
            if in_body and line.startswith("## "):
                break
            if in_body:
                rendered += line + "\n"
        name = ""
        for line in raw.splitlines():
            if line.startswith("# Prompt: "):
                name = line[10:].strip()
                break
        return PromptContent(prompt_def_name=name, rendered_text=rendered.strip())
