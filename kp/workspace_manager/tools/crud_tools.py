"""MCP tool implementations for general typed-artifact CRUD (the 9 ported types).

Ported from artifact_repo's original (pre-indexed-entry-rework) crud_tools.py.
Operates on whatever branch the GitStore session is currently checked out to —
typically 'main', but works the same on a workspace branch too.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from workspace_manager.store.git_store import GitStore
from workspace_manager.types.base import ArtifactMetadata
from workspace_manager.types.registry import get_artifact_class


def tool_list_packages(store: GitStore) -> list[str]:
    """Return the names of all packages in the repository."""
    return store.list_packages()


def tool_list_artifacts(
    store: GitStore,
    package: str,
    type_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List artifact metadata entries in a package."""
    return store.list_artifacts(package, type_filter=type_filter, name_filter=name_filter, limit=limit)


def tool_read_artifact(store: GitStore, package: str, artifact_id: str) -> dict[str, Any]:
    """Read a single artifact by id. Returns {metadata, content_str, type}."""
    content_str, meta = store.read_content_str(package, artifact_id)
    return {
        "metadata": json.loads(meta.model_dump_json()),
        "content_str": content_str,
        "type": meta.type,
    }


def tool_write_artifact(
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
    """Write (create or overwrite) an artifact on the session's current branch.

    Content format by type: CSV for table, YAML for yaml/arcadia_fabric, Markdown
    for text/session_summary/prompt, JSON for prompt_def/json/others.
    """
    cls = get_artifact_class(type)
    try:
        content = cls.deserialize_content(content_str)
    except Exception as exc:
        return {"error": f"Content validation failed for type '{type}': {exc}"}

    meta = ArtifactMetadata(
        type=type, name=name, package_name=package,
        tags=tags or [], source_tool=source_tool, lineage=lineage or [],
    )
    if artifact_id:
        meta.artifact_id = artifact_id

    artifact = cls(metadata=meta, content=content)
    art_dir = store.write(artifact)

    return {"artifact_id": meta.artifact_id, "path": str(art_dir), "type": type, "name": name}


def tool_delete_artifact(store: GitStore, package: str, artifact_id: str) -> dict[str, str]:
    """Delete an artifact from the repository."""
    try:
        store.delete(package, artifact_id)
        return {"status": "deleted", "artifact_id": artifact_id}
    except KeyError as exc:
        return {"status": "not_found", "error": str(exc)}


def tool_get_artifact_versions(store: GitStore, package: str, artifact_id: str) -> list[dict[str, str]]:
    """Return git commit history for an artifact."""
    return store.get_artifact_versions(artifact_id)


def tool_search_artifacts(
    store: GitStore,
    package: str,
    query: str,
    type_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Full-text search across artifact names, tags, and content files."""
    return store.search_artifacts(package, query, type_filter=type_filter)


def tool_push_artifacts(store: GitStore) -> dict[str, str]:
    """Push all locally committed artifacts to the remote repository."""
    if not isinstance(store, GitStore):
        return {"status": "error", "message": "Git is not enabled for this store"}
    return store.push()
