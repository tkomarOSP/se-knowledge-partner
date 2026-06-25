"""Indexed-entry storage for the 4 Knowledge-layer types.

Replaces the old monolithic ``log_book`` (single content.md, read-modify-write
on every append) with a per-package ``index.json`` manifest plus one ``.md``
file per entry under ``entries/``. Applies to ``observation``, ``decision``,
``lesson_learned``, and ``routine_def`` — the 4 types that remain in
artifact_repo after the indexed-entry rework. Everything else lives in
workspace_manager.

Layout::

    packages/<package>/
    ├── index.json
    └── entries/
        ├── obs-0001-<uuid>.md
        ├── dec-0001-<uuid>.md
        └── ...
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional


_PREFIX_MAP = {
    "observation": "obs",
    "decision": "dec",
    "lesson_learned": "lesson",
    "routine_def": "routine",
}


def _prefix_for(entry_type: str) -> str:
    return _PREFIX_MAP.get(entry_type, "note")


class IndexedEntryStore:
    """Per-package index.json + entries/*.md storage for the 4 Knowledge types."""

    def __init__(self, root: Path):
        self.root = root

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _package_dir(self, package: str) -> Path:
        return self.root / "packages" / package

    def _index_path(self, package: str) -> Path:
        return self._package_dir(package) / "index.json"

    def is_migrated(self, package: str) -> bool:
        return self._index_path(package).exists()

    # ------------------------------------------------------------------
    # Index I/O
    # ------------------------------------------------------------------

    def load_index(self, package: str) -> dict[str, Any]:
        path = self._index_path(package)
        if not path.exists():
            return {"package": package, "entry_count": 0, "entries": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_index(self, package: str, idx: dict[str, Any]) -> None:
        path = self._index_path(package)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(idx, indent=2, default=str), encoding="utf-8")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write_entry(
        self,
        package: str,
        entry_type: str,
        title: str,
        body_markdown: str,
        tags: Optional[list[str]] = None,
        author: Optional[str] = None,
        timestamp: Optional[str] = None,
        entry_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Write one entries/*.md file + append/update the package's index.json.

        If entry_id refers to an existing entry, overwrites that entry's file
        and index record in place rather than appending a new one.
        """
        from datetime import datetime, timezone  # noqa: PLC0415

        idx = self.load_index(package)
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tags = tags or []

        existing = None
        if entry_id:
            existing = next((e for e in idx["entries"] if e["id"] == entry_id), None)

        if existing:
            file_path = existing["file_path"]
            new_id = entry_id
        else:
            seq = 1 + sum(1 for e in idx["entries"] if e["type"] == entry_type)
            prefix = _prefix_for(entry_type)
            new_id = entry_id or f"{prefix}-{seq:04d}-{uuid.uuid4().hex}"
            file_path = f"entries/{new_id}.md"

        entries_dir = self._package_dir(package) / "entries"
        entries_dir.mkdir(parents=True, exist_ok=True)

        frontmatter = (
            "---\n"
            f"id: {new_id}\n"
            f"type: {entry_type}\n"
            f"timestamp: {ts}\n"
            f"author: {author or ''}\n"
            f"tags: {json.dumps(tags)}\n"
            "---\n\n"
        )
        (self._package_dir(package) / file_path).write_text(
            frontmatter + body_markdown.rstrip() + "\n", encoding="utf-8"
        )

        record = {
            "id": new_id,
            "type": entry_type,
            "timestamp": ts,
            "title": title[:60],
            "tags": tags,
            "file_path": file_path,
        }
        if existing:
            idx["entries"] = [record if e["id"] == new_id else e for e in idx["entries"]]
        else:
            idx["entries"].append(record)
        idx["package"] = package
        idx["entry_count"] = len(idx["entries"])
        self.save_index(package, idx)

        return record

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_entry(self, package: str, entry_id: str) -> tuple[str, dict[str, Any]]:
        idx = self.load_index(package)
        record = next((e for e in idx["entries"] if e["id"] == entry_id), None)
        if not record:
            raise KeyError(f"Entry '{entry_id}' not found in package '{package}'.")
        full_md = (self._package_dir(package) / record["file_path"]).read_text(encoding="utf-8")
        return full_md, record

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_entries(
        self,
        package: str,
        query: Optional[str] = None,
        type_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        since: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        idx = self.load_index(package)
        results = []
        q = (query or "").lower()
        for e in idx["entries"]:
            if type_filter and e["type"] != type_filter:
                continue
            if tag_filter and tag_filter not in e.get("tags", []):
                continue
            if since and e["timestamp"] < since:
                continue
            if q and q not in e["title"].lower():
                continue
            results.append({"artifact_id": e["id"], "package_name": package, **e})
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return results

    def list_entries(self, package: str, type_filter: Optional[str] = None) -> list[dict[str, Any]]:
        return self.search_entries(package, type_filter=type_filter)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_entry(self, package: str, entry_id: str) -> str:
        """Remove the entry file + its index record. Returns the relative file_path removed."""
        idx = self.load_index(package)
        record = next((e for e in idx["entries"] if e["id"] == entry_id), None)
        if not record:
            raise KeyError(f"Entry '{entry_id}' not found in package '{package}'.")
        file_path = record["file_path"]
        full_path = self._package_dir(package) / file_path
        if full_path.exists():
            full_path.unlink()
        idx["entries"] = [e for e in idx["entries"] if e["id"] != entry_id]
        idx["entry_count"] = len(idx["entries"])
        self.save_index(package, idx)
        return file_path

    # ------------------------------------------------------------------
    # Assembly (render_log_book)
    # ------------------------------------------------------------------

    def render_log_book(self, package: str, type_filter: Optional[str] = None) -> str:
        """Assemble all entries (any of the 4 types) into one Markdown doc, newest first."""
        idx = self.load_index(package)
        entries = idx["entries"]
        if type_filter:
            entries = [e for e in entries if e["type"] == type_filter]
        entries = sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)

        sections = [f"# Log — {package}", ""]
        for e in entries:
            full_md = (self._package_dir(package) / e["file_path"]).read_text(encoding="utf-8")
            # Strip the YAML frontmatter block, keep just the body for assembly.
            body = full_md.split("---\n\n", 1)[-1] if full_md.startswith("---\n") else full_md
            author = ""
            for line in full_md.splitlines():
                if line.startswith("author:"):
                    author = line.split(":", 1)[1].strip()
                    break
            header = f"## {e['timestamp']} — {e['type']}"
            if author:
                header += f" — {author}"
            sections.append("---")
            sections.append("")
            sections.append(header)
            sections.append("")
            sections.append(body.strip())
            sections.append("")
        return "\n".join(sections)
