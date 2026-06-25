"""Type-specific artifact content renderers for the KP viewer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import mistune
import yaml as _yaml

_md = mistune.create_markdown(plugins=["table", "strikethrough"])


def render_markdown(text: str) -> str:
    return _md(text) or ""


# ---------------------------------------------------------------------------
# Entry type badge helpers
# ---------------------------------------------------------------------------

BADGE_CLASSES = {
    "issue": "badge-issue",
    "decision": "badge-decision",
    "observation": "badge-observation",
    "milestone": "badge-milestone",
    "note": "badge-note",
    "running": "badge-running",
    "paused": "badge-paused",
    "complete": "badge-complete",
    "promoted": "badge-promoted",
}

TYPE_BADGE_CLASSES = {
    "log_book": "type-log-book",
    "routine_def": "type-routine",
    "text": "type-text",
    "table": "type-table",
    "yaml": "type-yaml",
    "decision": "type-decision",
    "observation": "type-observation",
    "lesson_learned": "type-lesson",
    "session_summary": "type-session",
}


def badge_class(entry_type: str) -> str:
    return BADGE_CLASSES.get(entry_type.lower(), "badge-note")


# ---------------------------------------------------------------------------
# Log book parser
# ---------------------------------------------------------------------------

@dataclass
class LogEntry:
    timestamp: datetime
    timestamp_str: str       # human-readable
    timestamp_iso: str       # raw ISO string for sorting
    entry_type: str
    body_html: str
    sequence: int = 0        # original order (for stable sort)
    author: str = ""         # engineer/agent name, if the entry header included one


def _format_ts(ts: datetime) -> str:
    return ts.strftime("%b %d, %Y at %I:%M %p UTC").replace(" 0", " ")


def parse_log_book(content: str, filter_type: Optional[str] = None) -> tuple[str, list[LogEntry], dict[str, int]]:
    """Parse log book Markdown into (header_html, entries, type_counts).

    Entries are returned most-recent-first. filter_type restricts to one entry_type.
    """
    # Split on horizontal rules used as entry separators
    sections = re.split(r'\n---+\n', content)

    header_html = render_markdown(sections[0].strip()) if sections else ""
    entries: list[LogEntry] = []
    type_counts: dict[str, int] = {}

    for seq, section in enumerate(sections[1:], start=1):
        section = section.strip()
        if not section:
            continue

        lines = section.split("\n")
        first_line = lines[0].strip()

        # Match:  ## 2026-06-13T13:56:28Z — decision [— author]
        m = re.match(r'^## (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) — (\S+)(?: — (.+))?$', first_line)
        if not m:
            continue

        ts_iso = m.group(1)
        entry_type = m.group(2).lower()
        author = (m.group(3) or "").strip()
        body_md = "\n".join(lines[1:]).strip()

        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

        if filter_type and entry_type != filter_type.lower():
            continue

        try:
            ts = datetime.strptime(ts_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            ts = datetime.min.replace(tzinfo=timezone.utc)

        entries.append(LogEntry(
            timestamp=ts,
            timestamp_str=_format_ts(ts),
            timestamp_iso=ts_iso,
            entry_type=entry_type,
            body_html=render_markdown(body_md),
            sequence=seq,
            author=author,
        ))

    # Most recent first; stable secondary sort by sequence descending
    entries.sort(key=lambda e: (e.timestamp, e.sequence), reverse=True)

    return header_html, entries, type_counts


# ---------------------------------------------------------------------------
# Routine def parser
# ---------------------------------------------------------------------------

@dataclass
class RoutineView:
    raw_yaml: str
    id: str = ""
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    variables: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    pre_flight: list[dict] = field(default_factory=list)
    post_execution: list[dict] = field(default_factory=list)
    prompt_template: str = ""
    parse_error: str = ""


def parse_routine_def(content: str) -> RoutineView:
    view = RoutineView(raw_yaml=content)
    try:
        parsed = _yaml.safe_load(content)
        rd = parsed.get("routine_def", {}) if isinstance(parsed, dict) else {}
        view.id = rd.get("id", "")
        view.name = rd.get("name", "")
        view.version = str(rd.get("version", ""))
        view.description = rd.get("description", "")
        view.author = rd.get("author", "")
        view.tags = rd.get("tags", [])
        view.variables = rd.get("variables", [])
        view.resources = rd.get("resources", [])
        view.inputs = rd.get("inputs", [])
        view.outputs = rd.get("outputs", [])
        view.pre_flight = rd.get("pre_flight", [])
        view.post_execution = rd.get("post_execution", [])
        view.prompt_template = rd.get("prompt_template", "")
    except Exception as exc:
        view.parse_error = str(exc)
    return view


# ---------------------------------------------------------------------------
# General renderers by artifact type
# ---------------------------------------------------------------------------

def render_text(content: str) -> str:
    """Render Markdown text artifact as HTML."""
    return render_markdown(content)


def render_html(content: str) -> str:
    """Render a raw HTML artifact as-is (no Markdown reinterpretation)."""
    return content


def render_table(content: str) -> str:
    """Render CSV table artifact as an HTML table."""
    import csv, io, html as _html
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return "<p><em>Empty table</em></p>"
    rows = list(reader)
    cols = reader.fieldnames
    th = "".join(f"<th>{_html.escape(c)}</th>" for c in cols)
    trs = ""
    for row in rows:
        tds = "".join(f"<td>{_html.escape(str(row.get(c, '')))}</td>" for c in cols)
        trs += f"<tr>{tds}</tr>"
    return f"<table class='csv-table'><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def render_json_artifact(content: str) -> str:
    """Render JSON artifact as a pretty-printed code block."""
    try:
        obj = json.loads(content)
        pretty = json.dumps(obj, indent=2)
    except Exception:
        pretty = content
    import html as _html
    return f"<pre class='code-block'>{_html.escape(pretty)}</pre>"


def render_yaml_artifact(content: str) -> str:
    """Render YAML artifact as a syntax-highlighted code block."""
    import html as _html
    return f"<pre class='code-block'>{_html.escape(content)}</pre>"


def render_artifact_content(content_str: str, artifact_type: str) -> str:
    """Dispatch to the appropriate renderer; fall back to code block."""
    if artifact_type == "html":
        return render_html(content_str)
    if artifact_type in ("text", "session_summary"):
        return render_text(content_str)
    if artifact_type == "table":
        return render_table(content_str)
    if artifact_type in ("yaml", "arcadia_fabric"):
        return render_yaml_artifact(content_str)
    if artifact_type in ("observation", "decision", "lesson_learned", "json", "prompt_def", "prompt"):
        return render_json_artifact(content_str)
    # fallback
    import html as _html
    return f"<pre class='code-block'>{_html.escape(content_str)}</pre>"
