"""Filesystem-backed artifact store.

Ported from artifact_repo/store/filesystem.py as part of the knowledge_repo
rework — unchanged layout, just relocated to workspace_manager since this is
now the general typed-artifact store used inside workspace branches.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from workspace_manager.types.base import ArtifactMetadata, BaseArtifact
from workspace_manager.types.registry import get_artifact_class


_INDEX_DIR = ".index"
_INDEX_FILE = "index.json"


class FilesystemStore:
    """CRUD operations on artifacts stored as files under a root directory.

    Layout::

        <root>/
        ├── .index/index.json
        └── packages/
            └── <package>/
                ├── package.json
                └── artifacts/
                    └── <YYYY-MM>/
                        └── <artifact_id>/
                            ├── artifact.json
                            └── content.<ext>
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / _INDEX_DIR / _INDEX_FILE
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._index_path.exists():
            self._index_path.write_text(json.dumps({}), encoding="utf-8")

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------

    def _load_index(self) -> dict[str, Any]:
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _save_index(self, idx: dict[str, Any]) -> None:
        self._index_path.write_text(json.dumps(idx, indent=2, default=str), encoding="utf-8")

    def _artifact_dir(self, metadata: ArtifactMetadata) -> Path:
        month = metadata.created_at.strftime("%Y-%m")
        return (
            self.root
            / "packages"
            / metadata.package_name
            / "artifacts"
            / month
            / metadata.artifact_id
        )

    # ------------------------------------------------------------------
    # Package management
    # ------------------------------------------------------------------

    def list_packages(self) -> list[str]:
        pkgs_dir = self.root / "packages"
        if not pkgs_dir.exists():
            return []
        return sorted(p.name for p in pkgs_dir.iterdir() if p.is_dir())

    def ensure_package(self, package_name: str) -> None:
        pkg_dir = self.root / "packages" / package_name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        pkg_file = pkg_dir / "package.json"
        if not pkg_file.exists():
            pkg_file.write_text(
                json.dumps({"name": package_name, "created_at": datetime.now(timezone.utc).isoformat()}),
                encoding="utf-8",
            )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, artifact: BaseArtifact) -> Path:
        """Persist artifact to disk and update the index. Returns the artifact directory."""
        meta = artifact.metadata
        meta.updated_at = datetime.now(timezone.utc)

        self.ensure_package(meta.package_name)
        art_dir = self._artifact_dir(meta)
        art_dir.mkdir(parents=True, exist_ok=True)

        # Write metadata
        (art_dir / "artifact.json").write_text(
            meta.model_dump_json(indent=2), encoding="utf-8"
        )

        # Write content
        ext = artifact.content_extension()
        (art_dir / f"content.{ext}").write_text(
            artifact.serialize_content(), encoding="utf-8"
        )

        # Update index
        idx = self._load_index()
        idx[meta.artifact_id] = {
            "type": meta.type,
            "name": meta.name,
            "package_name": meta.package_name,
            "path": str(art_dir.relative_to(self.root)),
            "created_at": meta.created_at.isoformat(),
            "updated_at": meta.updated_at.isoformat(),
            "tags": meta.tags,
        }
        self._save_index(idx)

        return art_dir

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read(self, package_name: str, artifact_id: str) -> BaseArtifact:
        """Load an artifact from disk by id."""
        idx = self._load_index()
        if artifact_id not in idx:
            raise KeyError(f"Artifact '{artifact_id}' not found in index.")

        entry = idx[artifact_id]
        art_dir = self.root / entry["path"]

        meta = ArtifactMetadata.model_validate_json(
            (art_dir / "artifact.json").read_text(encoding="utf-8")
        )

        # Find content file
        content_files = list(art_dir.glob("content.*"))
        if not content_files:
            raise FileNotFoundError(f"No content file in {art_dir}")
        raw = content_files[0].read_text(encoding="utf-8")

        cls = get_artifact_class(meta.type)
        content = cls.deserialize_content(raw)
        return cls(metadata=meta, content=content)

    def read_content_str(self, package_name: str, artifact_id: str) -> tuple[str, ArtifactMetadata]:
        """Return raw content string and metadata (avoids full deserialization)."""
        idx = self._load_index()
        if artifact_id not in idx:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        art_dir = self.root / idx[artifact_id]["path"]
        meta = ArtifactMetadata.model_validate_json(
            (art_dir / "artifact.json").read_text(encoding="utf-8")
        )
        content_files = list(art_dir.glob("content.*"))
        if not content_files:
            raise FileNotFoundError(f"No content file in {art_dir}")
        return content_files[0].read_text(encoding="utf-8"), meta

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, package_name: str, artifact_id: str) -> None:
        idx = self._load_index()
        if artifact_id not in idx:
            raise KeyError(f"Artifact '{artifact_id}' not found.")

        art_dir = self.root / idx.pop(artifact_id)["path"]
        if art_dir.exists():
            import shutil
            shutil.rmtree(art_dir)
        self._save_index(idx)

    # ------------------------------------------------------------------
    # List / search
    # ------------------------------------------------------------------

    def list_artifacts(
        self,
        package_name: str,
        type_filter: Optional[str] = None,
        name_filter: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        idx = self._load_index()
        results = []
        for aid, entry in idx.items():
            if entry.get("package_name") != package_name:
                continue
            if type_filter and entry.get("type") != type_filter:
                continue
            if name_filter:
                name = entry.get("name") or ""
                if name_filter.lower() not in name.lower():
                    continue
            results.append({"artifact_id": aid, **entry})

        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results[:limit]

    def search_artifacts(
        self,
        package_name: str,
        query: str,
        type_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Simple full-text search: scans index name/tags, then content files."""
        q = query.lower()
        idx = self._load_index()
        results = []

        for aid, entry in idx.items():
            if entry.get("package_name") != package_name:
                continue
            if type_filter and entry.get("type") != type_filter:
                continue

            # Check name and tags first (fast)
            name_hit = q in (entry.get("name") or "").lower()
            tag_hit = any(q in t.lower() for t in entry.get("tags", []))

            # Check content file (slower)
            content_hit = False
            try:
                art_dir = self.root / entry["path"]
                for cf in art_dir.glob("content.*"):
                    if q in cf.read_text(encoding="utf-8", errors="ignore").lower():
                        content_hit = True
                        break
            except Exception:
                pass

            if name_hit or tag_hit or content_hit:
                results.append({"artifact_id": aid, **entry})

        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results

    # ------------------------------------------------------------------
    # Artifact directory path (for git staging)
    # ------------------------------------------------------------------

    def artifact_dir_path(self, artifact_id: str) -> Optional[Path]:
        idx = self._load_index()
        entry = idx.get(artifact_id)
        if not entry:
            return None
        return self.root / entry["path"]
