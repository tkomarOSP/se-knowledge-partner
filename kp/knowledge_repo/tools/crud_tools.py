"""MCP tool implementations for the knowledge_repo (4 Knowledge-layer types).

These functions are registered with FastMCP in server.py. All 4 types
(observation, decision, lesson_learned, routine_def) are persisted via
IndexedEntryStore (see store/indexed_entries.py), reached through GitStore's
``entries`` attribute — never through the old per-artifact-directory
FilesystemStore layout. The other 9 artifact types (table, yaml, text, html,
arcadia_fabric, session_summary, prompt_def, prompt, json) are no longer
supported here; they live in workspace_manager.
"""

from __future__ import annotations

from typing import Any, Optional

from jinja2 import Template

from knowledge_repo.store.git_store import GitStore

_KNOWLEDGE_TYPES = {"observation", "decision", "lesson_learned", "routine_def"}

_NOT_SUPPORTED_MSG = (
    "Type '{type}' is no longer supported by knowledge_repo. "
    "knowledge_repo now only stores observation/decision/lesson_learned/routine_def "
    "via add_log_entry. Use workspace_manager.write_workspace_artifact for "
    "table/yaml/text/html/json/arcadia_fabric/session_summary/prompt_def/prompt artifacts."
)


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
    """List knowledge entries in a package (observation/decision/lesson_learned/routine_def).

    Args:
        package: Package name to query.
        type_filter: If provided, return only entries of this type.
        name_filter: If provided, return only entries whose title contains this substring.
        limit: Maximum number of results (default 100).
    """
    results = store.entries.list_entries(package, type_filter=type_filter)
    if name_filter:
        nf = name_filter.lower()
        results = [r for r in results if nf in r.get("title", "").lower()]
    return results[:limit]


def tool_read_repo_artifact(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> dict[str, Any]:
    """Read a single knowledge entry by id.

    Returns a dict with keys: ``metadata`` (dict), ``content_str`` (str), ``type`` (str).
    """
    try:
        full_md, record = store.entries.read_entry(package, artifact_id)
    except KeyError as exc:
        return {"error": str(exc)}
    return {
        "metadata": {"artifact_id": record["id"], "package_name": package, **record},
        "content_str": full_md,
        "type": record["type"],
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
    """Write (create or overwrite) a knowledge entry.

    Args:
        package: Package name (created automatically if it does not exist).
        type: Must be one of observation/decision/lesson_learned/routine_def.
        name: Human-readable title for the entry.
        content_str: Markdown body (or YAML body for routine_def).
        tags: Optional list of tag strings.
        source_tool: Name of the tool/author attributed to this entry.
        lineage: Unused for indexed entries — kept for call-signature compatibility.
        artifact_id: Provide to overwrite an existing entry by ID; omit to create new.
    """
    if type not in _KNOWLEDGE_TYPES:
        return {"error": _NOT_SUPPORTED_MSG.format(type=type)}

    record = store.write_entry(
        package, entry_type=type, title=name, body_markdown=content_str,
        tags=tags, author=source_tool, entry_id=artifact_id,
    )
    return {
        "artifact_id": record["id"],
        "path": record["file_path"],
        "type": type,
        "name": name,
    }


def tool_delete_repo_artifact(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> dict[str, str]:
    """Delete a knowledge entry from the repository.

    Args:
        package: Package name.
        artifact_id: ID of the entry to delete.
    """
    try:
        store.delete_entry(package, artifact_id)
        return {"status": "deleted", "artifact_id": artifact_id}
    except KeyError as exc:
        return {"status": "not_found", "error": str(exc)}


def tool_get_repo_artifact_versions(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> list[dict[str, str]]:
    """Return git commit history for a knowledge entry.

    Returns an empty list if the store is not git-backed or the entry has no history.

    Args:
        package: Package name.
        artifact_id: ID of the entry.
    """
    return store.get_entry_versions(package, artifact_id)


def tool_search_repo_artifacts(
    store: GitStore,
    package: str,
    query: str,
    type_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Search knowledge entries by title substring (index-only — does not open entry files).

    Args:
        package: Package name to search.
        query: Case-insensitive substring to match against entry titles.
        type_filter: If provided, restrict results to this entry type.
    """
    return store.entries.search_entries(package, query=query, type_filter=type_filter)


def tool_push_repo_artifacts(store: GitStore) -> dict[str, str]:
    """Push all locally committed artifacts to the remote GitHub repository.

    Call this at session end or on demand. Requires connect_repo to have been
    called first in this session.
    """
    if not isinstance(store, GitStore):
        return {"status": "error", "message": "Git is not enabled for this store"}
    return store.push()


def _format_artifact_ref(ref: Any) -> str:
    """Render one related_artifacts entry for inclusion in an entry body.

    `ref` is either a bare artifact_id string (local knowledge_repo entry — rendered
    as a code span, since indexed entries have no fixed URL pattern without a viewer
    base URL in scope here) or a dict of the cross-service reference form
    {"workspace_branch", "package", "artifact_id", "viewer_url"} for objects living in
    workspace_manager — rendered as a link using viewer_url when present.
    """
    if isinstance(ref, dict):
        label = ref.get("artifact_id", "?")[:8]
        branch = ref.get("workspace_branch", "")
        viewer_url = ref.get("viewer_url")
        text = f"{label} (workspace:{branch})"
        return f"[{text}]({viewer_url})" if viewer_url else f"`{text}`"
    return f"`{ref}`"


def tool_add_log_entry(
    store: GitStore,
    package: str,
    text: str,
    entry_type: str = "note",
    artifact_refs: Optional[list[Any]] = None,
    author: Optional[str] = None,
) -> dict[str, Any]:
    """Write a new knowledge entry (observation/decision/lesson_learned/note/etc.).

    Writes a new entries/*.md file and appends a record to the package's index.json
    — no read-modify-write of a monolithic log_book file (that storage model no longer
    exists; see the knowledge_repo indexed-entry rework).

    Args:
        package: Package name.
        text: Entry body text (Markdown).
        entry_type: Category label (e.g. "note", "milestone", "observation", "decision",
                    "lesson_learned", "issue").
        artifact_refs: Optional list of references to cite — either bare artifact_id
            strings (other knowledge_repo entries) or cross-service reference dicts
            {"workspace_branch", "package", "artifact_id", "viewer_url"} pointing at
            workspace_manager objects.
        author: Optional engineer/agent name to attribute this entry to.
    """
    if author and ("\n" in author or " — " in author):
        return {"error": "author must not contain newlines or ' — '"}

    body = text
    if artifact_refs:
        refs_str = ", ".join(_format_artifact_ref(r) for r in artifact_refs)
        body = f"{text}\n\n**References:** {refs_str}"

    record = store.write_entry(
        package, entry_type=entry_type, title=text[:60], body_markdown=body, author=author,
    )
    return {
        "status": "ok",
        "entry_id": record["id"],
        "entry_type": entry_type,
        "timestamp": record["timestamp"],
        "author": author,
    }


def tool_read_entry(store: GitStore, package: str, entry_id: str) -> dict[str, Any]:
    """Fetch one knowledge entry (observation/decision/lesson_learned/routine_def) by id.

    Args:
        package: Package name.
        entry_id: ID of the entry (see index entries returned by browse_knowledge_repo).
    """
    try:
        full_md, record = store.entries.read_entry(package, entry_id)
    except KeyError as exc:
        return {"error": str(exc)}
    return {"content_str": full_md, "metadata": {"package_name": package, **record}}


def tool_render_log_book(
    store: GitStore,
    package: str,
    type_filter: Optional[str] = None,
) -> dict[str, Any]:
    """Assemble all knowledge entries for a package into one rendered log, newest first.

    Args:
        package: Package name.
        type_filter: Restrict the assembled log to one entry type.
    """
    rendered = store.entries.render_log_book(package, type_filter=type_filter)
    return {"rendered_markdown": rendered}


def _strip_entry_body(full_md: str) -> str:
    """Return just the body of an entries/*.md file (everything after the frontmatter block)."""
    return full_md.split("---\n\n", 1)[-1] if full_md.startswith("---\n") else full_md


def tool_validate_routine_def(
    store: GitStore,
    package: str,
    artifact_id: str,
) -> dict[str, Any]:
    """Validate the schema of a routine_def entry without executing it.

    Checks structural completeness only — does not verify resource accessibility.
    Returns {valid, errors, warnings, passed, summary}. `passed` lists fields/sections
    that validated cleanly, so iterative authoring can confirm a fix didn't regress
    something else. Unrecognized top-level keys that look like typos of a known field
    (e.g. 'pre_flight_checks') surface as warnings with a suggested correction.

    Args:
        package: Package name.
        artifact_id: id of the routine_def entry to validate.
    """
    import difflib  # noqa: PLC0415
    import yaml  # noqa: PLC0415

    try:
        full_md, record = store.entries.read_entry(package, artifact_id)
    except KeyError as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": [], "passed": [], "summary": {}}

    if record["type"] != "routine_def":
        return {
            "valid": False,
            "errors": [f"Entry {artifact_id} is type '{record['type']}', expected 'routine_def'"],
            "warnings": [],
            "passed": [],
            "summary": {},
        }
    content_str = _strip_entry_body(full_md)

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
        hits = store.entries.list_entries(pkg, type_filter="routine_def")
        for entry_dict in hits:
            aid = entry_dict.get("id", entry_dict.get("artifact_id", ""))
            version = None
            description = None
            try:
                full_md, _ = store.entries.read_entry(pkg, aid)
                parsed = yaml.safe_load(_strip_entry_body(full_md))
                rd = parsed.get("routine_def", {}) if isinstance(parsed, dict) else {}
                version = rd.get("version")
                description = rd.get("description")
            except Exception:
                pass
            results.append({
                "artifact_id": aid,
                "name": entry_dict.get("title"),
                "package": pkg,
                "version": version,
                "description": description,
                "tags": entry_dict.get("tags", []),
                "updated_at": entry_dict.get("timestamp"),
            })

    return results


# NOTE: render_prompt (prompt_def lookup + Jinja2 render) moves to workspace_manager
# along with the prompt_def/prompt types — knowledge_repo no longer stores either.


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
         or {"found": False, "message": ...} if the entry is missing or not a routine_def.

    Args:
        package: Package name.
        artifact_id: id of the routine_def entry to render.
        variables: Dict of variable values to substitute into the template; merged
                   over each declared variable's 'default' value.
    """
    import yaml  # noqa: PLC0415

    try:
        full_md, record = store.entries.read_entry(package, artifact_id)
    except KeyError as exc:
        return {"found": False, "message": str(exc)}

    if record["type"] != "routine_def":
        return {"found": False, "message": f"Entry {artifact_id} is type '{record['type']}', expected 'routine_def'"}
    content_str = _strip_entry_body(full_md)

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
