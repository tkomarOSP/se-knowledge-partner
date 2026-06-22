"""MCP tool implementations for artifact repository CRUD.

These functions are registered with FastMCP in server.py.
They delegate all persistence to FilesystemStore / GitStore.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from jinja2 import Template

from artifact_repo.store.git_store import GitStore
from artifact_repo.types.base import ArtifactMetadata
from artifact_repo.types.common import PromptArtifact, PromptContent, PromptDefContent
from artifact_repo.types.registry import get_artifact_class, list_registered_types


def _store(git_store: GitStore):
    """Return the shared store instance (injected at import time by server.py)."""
    return git_store


# ---------------------------------------------------------------------------
# Tool implementations (called from server.py @mcp.tool() wrappers)
# ---------------------------------------------------------------------------

_KNOWN_ROUTINE_DEF_FIELDS = {
    "id", "name", "version", "description", "prompt_template",
    "variables", "resources", "outputs", "pre_flight", "post_execution", "tags",
}

def tool_list_repo_packages(store: GitStore) -> list[str]:
    """Return the names of all packages in the repository."""
    return store.list_packages()


def tool_list_repo_artifacts(
    store: GitStore,
    package: str,
    type_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List artifact metadata entries in a package.

    Args:
        package: Package name to query.
        type_filter: If provided, return only artifacts of this type.
        name_filter: If provided, return only artifacts whose name contains this substring.
        limit: Maximum number of results (default 100).
    """
    return store.list_artifacts(package, type_filter=type_filter, name_filter=name_filter, limit=limit)


def tool_read_repo_artifact(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> dict[str, Any]:
    """Read a single artifact by id.

    Returns a dict with keys: ``metadata`` (dict), ``content_str`` (str), ``type`` (str).
    """
    content_str, meta = store.read_content_str(package, artifact_id)
    return {
        "metadata": json.loads(meta.model_dump_json()),
        "content_str": content_str,
        "type": meta.type,
    }


def tool_write_repo_artifact(
    store: GitStore,
    package: str,
    type: str,
    name: str,
    content_str: str,
    tags: Optional[list[str]] = None,
    source_tool: Optional[str] = None,
    lineage: Optional[list[str]] = None,
    artifact_id: Optional[str] = None,
) -> dict[str, Any]:
    """Write (create or overwrite) an artifact.

    The ``content_str`` is validated against the registered Pydantic type for
    ``type``. If the type is unrecognised it falls back to ``JsonArtifact``.

    Args:
        package: Package name (created automatically if it does not exist).
        type: Artifact type string (e.g. ``table``, ``yaml``, ``arcadia_fabric``).
        name: Human-readable name for the artifact.
        content_str: Serialized content string (CSV for tables, YAML/text/html as-is, JSON otherwise).
        tags: Optional list of tag strings.
        source_tool: Name of the tool that produced this artifact.
        lineage: Parent artifact IDs this artifact was derived from.
        artifact_id: Provide to overwrite an existing artifact by ID; omit to create new.
    """
    cls = get_artifact_class(type)

    # Deserialize and validate content
    try:
        content = cls.deserialize_content(content_str)
    except Exception as exc:
        return {"error": f"Content validation failed for type '{type}': {exc}"}

    meta = ArtifactMetadata(
        type=type,
        name=name,
        package_name=package,
        tags=tags or [],
        source_tool=source_tool,
        lineage=lineage or [],
    )
    if artifact_id:
        meta.artifact_id = artifact_id

    artifact = cls(metadata=meta, content=content)
    art_dir = store.write(artifact)

    return {
        "artifact_id": meta.artifact_id,
        "path": str(art_dir),
        "type": type,
        "name": name,
    }


def tool_delete_repo_artifact(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> dict[str, str]:
    """Delete an artifact from the repository.

    Args:
        package: Package name.
        artifact_id: ID of the artifact to delete.
    """
    try:
        store.delete(package, artifact_id)
        return {"status": "deleted", "artifact_id": artifact_id}
    except KeyError as exc:
        return {"status": "not_found", "error": str(exc)}


def tool_get_repo_artifact_versions(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> list[dict[str, str]]:
    """Return git commit history for an artifact.

    Returns an empty list if the store is not git-backed or the artifact has no history.

    Args:
        package: Package name.
        artifact_id: ID of the artifact.
    """
    return store.get_artifact_versions(artifact_id)


def tool_search_repo_artifacts(
    store: GitStore,
    package: str,
    query: str,
    type_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Full-text search across artifact names, tags, and content files.

    Args:
        package: Package name to search.
        query: Search string (case-insensitive substring match).
        type_filter: If provided, restrict results to this artifact type.
    """
    return store.search_artifacts(package, query, type_filter=type_filter)


def tool_push_repo_artifacts(store: GitStore) -> dict[str, str]:
    """Push all locally committed artifacts to the remote GitHub repository.

    Call this at session end or on demand. Requires connect_repo to have been
    called first in this session.
    """
    if not isinstance(store, GitStore):
        return {"status": "error", "message": "Git is not enabled for this store"}
    return store.push()


def tool_add_log_entry(
    store: GitStore,
    package: str,
    log_book_id: str,
    text: str,
    entry_type: str = "note",
    artifact_refs: Optional[list[str]] = None,
    author: Optional[str] = None,
) -> dict[str, Any]:
    """Append a timestamped entry to a log_book artifact.

    Reads the current Markdown content, appends a formatted section with a UTC
    timestamp, and writes back using the same artifact_id (overwrite).

    Args:
        package: Package name.
        log_book_id: artifact_id of the log_book artifact to append to.
        text: Entry body text.
        entry_type: Category label shown in the section header (e.g. "note", "milestone",
                    "observation", "decision").
        artifact_refs: Optional list of artifact_ids to cite in the entry.
        author: Optional engineer/agent name to attribute this entry to. Appears in the
                header line when provided; omitted entirely (preserving the old format)
                when not — a log_book may be shared across engineers and agents.
    """
    if author and ("\n" in author or " — " in author):
        return {"error": "author must not contain newlines or ' — '"}

    try:
        content_str, meta = store.read_content_str(package, log_book_id)
    except KeyError as exc:
        return {"error": str(exc)}

    if meta.type != "log_book":
        return {"error": f"Artifact {log_book_id} is type '{meta.type}', expected 'log_book'"}

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = f"## {ts} — {entry_type}"
    if author:
        header += f" — {author}"
    section_lines = [f"\n---\n\n{header}\n\n{text}"]
    if artifact_refs:
        _EXT_MAP = {
            "table": "csv", "yaml": "yaml", "arcadia_fabric": "yaml",
            "text": "md", "html": "html", "session_summary": "md", "log_book": "md", "prompt": "md",
            "prompt_def": "json", "observation": "json", "decision": "json",
            "lesson_learned": "json", "json": "json",
        }
        idx = store._load_index()
        ref_links = []
        for r in artifact_refs:
            entry = idx.get(r)
            if entry:
                name = entry.get("name") or r[:8]
                type_ = entry.get("type", "json")
                path = entry.get("path", "")
                ext = _EXT_MAP.get(type_, "json")
                ref_links.append(f"[{name} ({type_})](/{path}/content.{ext})")
            else:
                ref_links.append(f"`{r}`")
        refs_str = ", ".join(ref_links)
        section_lines.append(f"\n**References:** {refs_str}")
    section_lines.append("")

    new_content = content_str.rstrip() + "\n" + "\n".join(section_lines)

    result = tool_write_repo_artifact(
        store, package, "log_book", meta.name or "log_book", new_content,
        tags=meta.tags, source_tool="add_log_entry", lineage=meta.lineage,
        artifact_id=log_book_id,
    )
    if "error" in result:
        return result
    return {"status": "ok", "log_book_id": log_book_id, "entry_type": entry_type, "timestamp": ts, "author": author}


def tool_validate_routine_def(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> dict[str, Any]:
    """Validate the schema of a routine_def artifact without executing it.

    Checks structural completeness only — does not verify resource accessibility.
    Returns {valid, errors, warnings, passed, summary}. `passed` lists fields/sections
    that validated cleanly, so iterative authoring can confirm a fix didn't regress
    something else. Unrecognized top-level keys that look like typos of a known field
    (e.g. 'pre_flight_checks') surface as warnings with a suggested correction.

    Args:
        package: Package name.
        artifact_id: artifact_id of the routine_def to validate.
    """
    import difflib  # noqa: PLC0415
    import yaml  # noqa: PLC0415

    try:
        content_str, meta = store.read_content_str(package, artifact_id)
    except KeyError as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": [], "passed": [], "summary": {}}

    if meta.type != "routine_def":
        return {
            "valid": False,
            "errors": [f"Artifact {artifact_id} is type '{meta.type}', expected 'routine_def'"],
            "warnings": [],
            "passed": [],
            "summary": {},
        }

    try:
        parsed = yaml.safe_load(content_str)
    except yaml.YAMLError as exc:
        return {"valid": False, "errors": [f"YAML parse error: {exc}"], "warnings": [], "passed": [], "summary": {}}

    errors: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []

    if not isinstance(parsed, dict) or "routine_def" not in parsed:
        return {
            "valid": False,
            "errors": ["Missing top-level 'routine_def' key"],
            "warnings": [],
            "passed": [],
            "summary": {},
        }

    rd = parsed["routine_def"]

    # Unrecognized top-level keys — advisory only, never an error (forward-compat)
    if isinstance(rd, dict):
        for uk in rd.keys():
            if uk in _KNOWN_ROUTINE_DEF_FIELDS:
                continue
            close = difflib.get_close_matches(uk, _KNOWN_ROUTINE_DEF_FIELDS, n=1, cutoff=0.6)
            if close:
                warnings.append(f"Unrecognized field 'routine_def.{uk}' — did you mean 'routine_def.{close[0]}'?")
            else:
                warnings.append(f"Unrecognized field 'routine_def.{uk}' — not a known routine_def field")

    # Required identity fields
    for field in ("id", "name", "version", "prompt_template"):
        if field not in rd:
            errors.append(f"Missing required field: routine_def.{field}")
        else:
            passed.append(f"routine_def.{field} present")
    if "description" not in rd:
        warnings.append("No 'description' field — recommended for discoverability")
    else:
        passed.append("routine_def.description present")

    # Variables
    variables = rd.get("variables", [])
    for i, v in enumerate(variables):
        if not isinstance(v, dict):
            errors.append(f"variables[{i}] must be a mapping")
            continue
        missing_vf = [vf for vf in ("name", "type", "required") if vf not in v]
        for vf in missing_vf:
            errors.append(f"variables[{i}] missing field: '{vf}'")
        if not missing_vf:
            passed.append(f"variables[{i}] ('{v.get('name')}') schema OK")
        if v.get("required") and "default" in v:
            warnings.append(f"variables[{i}] ('{v.get('name')}') is required but has a default — default will be ignored if value not provided")

    # Resources (optional section)
    resources = rd.get("resources", [])
    for i, r in enumerate(resources):
        if not isinstance(r, dict):
            errors.append(f"resources[{i}] must be a mapping")
            continue
        missing_rf = [rf for rf in ("id", "type", "mcp_tool") if rf not in r]
        for rf in missing_rf:
            errors.append(f"resources[{i}] missing field: '{rf}'")
        if not missing_rf:
            passed.append(f"resources[{i}] ('{r.get('id')}') schema OK")

    # Outputs
    outputs = rd.get("outputs", [])
    if not outputs:
        warnings.append("No 'outputs' declared — routine produces no artifacts")
    else:
        has_required = False
        for i, o in enumerate(outputs):
            if not isinstance(o, dict):
                errors.append(f"outputs[{i}] must be a mapping")
                continue
            missing_of = [of for of in ("name", "type", "package") if of not in o]
            for of in missing_of:
                errors.append(f"outputs[{i}] missing field: '{of}'")
            if not missing_of:
                passed.append(f"outputs[{i}] ('{o.get('name')}') schema OK")
            if o.get("required"):
                has_required = True
        if has_required:
            passed.append("at least one output marked required: true")
        else:
            warnings.append("No output has 'required: true' — consider marking at least one output as required")

    # prompt_template non-empty
    pt = rd.get("prompt_template", "")
    if isinstance(pt, str) and not pt.strip():
        errors.append("prompt_template is empty")
    else:
        passed.append("prompt_template non-empty")

    summary = {
        "id": rd.get("id"),
        "name": rd.get("name"),
        "version": rd.get("version"),
        "variable_count": len(variables),
        "resource_count": len(resources),
        "output_count": len(outputs),
        "has_pre_flight": bool(rd.get("pre_flight")),
        "has_post_execution": bool(rd.get("post_execution")),
    }

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "passed": passed,
        "summary": summary,
    }


def tool_list_routines(
    store: GitStore,
    package: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List all routine_def artifacts, optionally filtered to a single package.

    If package is omitted, searches all packages in the repository.
    Returns a concise list: artifact_id, name, package, version, description, tags.

    Args:
        package: Package name to restrict the search; omit to search all packages.
    """
    import yaml  # noqa: PLC0415

    packages = [package] if package else store.list_packages()
    results: list[dict[str, Any]] = []

    for pkg in packages:
        hits = store.list_artifacts(pkg, type_filter="routine_def")
        for meta_dict in hits:
            aid = meta_dict.get("artifact_id", "")
            version = None
            description = None
            try:
                content_str, _ = store.read_content_str(pkg, aid)
                parsed = yaml.safe_load(content_str)
                rd = parsed.get("routine_def", {}) if isinstance(parsed, dict) else {}
                version = rd.get("version")
                description = rd.get("description")
            except Exception:
                pass
            results.append({
                "artifact_id": aid,
                "name": meta_dict.get("name"),
                "package": pkg,
                "version": version,
                "description": description,
                "tags": meta_dict.get("tags", []),
                "updated_at": meta_dict.get("updated_at"),
            })

    return results


def tool_render_prompt(
    store: GitStore,
    package: str,
    prompt_name: str,
    variables: Optional[dict] = None,
    save_rendered: bool = False,
    source: str = "local",
) -> dict[str, Any]:
    """Find a prompt_def artifact by name, render it with Jinja2, optionally save result.

    Returns {"found": True, "rendered": text, "prompt_artifact_id": id_or_None}
         or {"found": False, "message": ...} if no matching prompt_def found.
    """
    hits = store.search_artifacts(package, prompt_name, type_filter="prompt_def")
    # pick exact name match first, then first partial match
    match = next((h for h in hits if h.get("name") == prompt_name), hits[0] if hits else None)
    if not match:
        return {"found": False, "message": f"No prompt_def named '{prompt_name}' in package '{package}'"}

    try:
        content_str, meta = store.read_content_str(package, match["artifact_id"])
        prompt_def = PromptDefContent.model_validate_json(content_str)
    except Exception as exc:
        return {"found": False, "message": f"Failed to read prompt_def: {exc}"}

    vars_with_defaults = {**prompt_def.defaults, **(variables or {})}
    try:
        rendered = Template(prompt_def.template).render(**vars_with_defaults)
    except Exception as exc:
        return {"found": True, "rendered": None, "error": f"Render failed: {exc}"}

    prompt_artifact_id = None
    if save_rendered:
        prompt_content = PromptContent(
            prompt_def_name=prompt_name,
            variables_used=vars_with_defaults,
            rendered_text=rendered,
            source=source,
        )
        prompt_meta = ArtifactMetadata(
            type="prompt",
            name=f"{prompt_name}-rendered",
            package_name=package,
            source_tool="render_prompt",
            lineage=[match["artifact_id"]],
        )
        artifact = PromptArtifact(metadata=prompt_meta, content=prompt_content)
        store.write(artifact)
        prompt_artifact_id = prompt_meta.artifact_id

    return {"found": True, "rendered": rendered, "prompt_artifact_id": prompt_artifact_id}


def tool_render_routine_prompt(
    store: GitStore,
    package: str,
    artifact_id: str,
    variables: Optional[dict] = None,
) -> dict[str, Any]:
    """Dry-run render of a routine_def's prompt_template via Jinja2 — template only, NOT full execution.

    Does not fetch resources, inputs, or Capella fabric data; it only merges
    engineer-supplied `variables` with each declared variable's `default` (from the
    routine_def's `variables` list) and renders the `prompt_template` string. Use this
    to catch Jinja2 syntax errors (typos in variable names, unclosed {% if %} blocks)
    before running the routine for real via the Routine Execution Protocol. The output
    is NOT equivalent to live execution — it will not reflect bound `inputs` or
    `resources`-derived fabric content.

    Returns {"found": True, "rendered": text, "error": None}
         or {"found": True, "rendered": None, "error": "Render failed: ..."} on Jinja2 error
         or {"found": False, "message": ...} if the artifact is missing or not a routine_def.

    Args:
        package: Package name.
        artifact_id: artifact_id of the routine_def to render.
        variables: Dict of variable values to substitute into the template; merged
                   over each declared variable's 'default' value.
    """
    import yaml  # noqa: PLC0415

    try:
        content_str, meta = store.read_content_str(package, artifact_id)
    except KeyError as exc:
        return {"found": False, "message": str(exc)}

    if meta.type != "routine_def":
        return {"found": False, "message": f"Artifact {artifact_id} is type '{meta.type}', expected 'routine_def'"}

    try:
        parsed = yaml.safe_load(content_str)
    except yaml.YAMLError as exc:
        return {"found": False, "message": f"YAML parse error: {exc}"}

    if not isinstance(parsed, dict) or "routine_def" not in parsed:
        return {"found": False, "message": "Missing top-level 'routine_def' key"}

    rd = parsed["routine_def"]
    prompt_template = rd.get("prompt_template", "")
    if not isinstance(prompt_template, str) or not prompt_template.strip():
        return {"found": True, "rendered": None, "error": "routine_def has no non-empty prompt_template"}

    declared_vars = rd.get("variables", []) or []
    defaults = {
        v.get("name"): v.get("default")
        for v in declared_vars
        if isinstance(v, dict) and v.get("name") is not None and "default" in v
    }
    vars_with_defaults = {**defaults, **(variables or {})}

    try:
        rendered = Template(prompt_template).render(**vars_with_defaults)
    except Exception as exc:
        return {"found": True, "rendered": None, "error": f"Render failed: {exc}"}

    return {"found": True, "rendered": rendered, "error": None}
