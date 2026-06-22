"""Prompt template storage and rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, StrictUndefined


class PromptStore:
    """Loads and renders Jinja2 prompt templates stored as JSON files.

    Each prompt file follows the schema::

        {
          "name": "my_prompt",
          "template": "Analyse {{ subject }} and return {{ format }}.",
          "vars": ["subject", "format"],
          "defaults": {"format": "JSON"},
          "tags": ["analysis"]
        }
    """

    SCHEMA_VERSION = 1

    def __init__(self, library_path: Path | str):
        self.path = Path(library_path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._env = Environment(undefined=StrictUndefined, autoescape=False)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_prompts(self, tag_filter: Optional[str] = None) -> list[dict[str, Any]]:
        results = []
        for f in self.path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if tag_filter and tag_filter not in data.get("tags", []):
                    continue
                results.append({
                    "name": data.get("name", f.stem),
                    "vars": data.get("vars", []),
                    "tags": data.get("tags", []),
                    "file": f.name,
                })
            except Exception:
                pass
        return sorted(results, key=lambda x: x["name"])

    def get_prompt(self, name: str) -> dict[str, Any]:
        path = self.path / f"{name}.json"
        if not path.exists():
            raise KeyError(f"Prompt '{name}' not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def save_prompt(self, spec: dict[str, Any]) -> None:
        required = {"name", "template", "vars"}
        missing = required - spec.keys()
        if missing:
            raise ValueError(f"Prompt spec missing required fields: {missing}")
        name = spec["name"]
        path = self.path / f"{name}.json"
        path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    def delete_prompt(self, name: str) -> None:
        path = self.path / f"{name}.json"
        if not path.exists():
            raise KeyError(f"Prompt '{name}' not found.")
        path.unlink()

    def render_prompt(self, name: str, vars: dict[str, Any]) -> str:
        spec = self.get_prompt(name)
        defaults = spec.get("defaults", {})
        context = {**defaults, **vars}
        tmpl = self._env.from_string(spec["template"])
        return tmpl.render(**context)

    def search_prompts(self, query: str) -> list[dict[str, Any]]:
        q = query.lower()
        results = []
        for f in self.path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                text = json.dumps(data).lower()
                if q in text:
                    results.append({
                        "name": data.get("name", f.stem),
                        "vars": data.get("vars", []),
                        "tags": data.get("tags", []),
                    })
            except Exception:
                pass
        return sorted(results, key=lambda x: x["name"])
