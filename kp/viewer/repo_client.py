"""Persistent read-only git clones of knowledge repos for the viewer, one per session."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from knowledge_repo.store.git_store import GitStore
from knowledge_repo.types.base import ArtifactMetadata


# Respect KP_VIEWER_BASE_DIR so clones land in a writable location on the server
# (e.g. /var/lib/kp-viewer). Falls back to ~/.kp_viewer locally.
_BASE_DIR = Path(os.environ.get("KP_VIEWER_BASE_DIR", "") or str(Path.home() / ".kp_viewer"))

# Per-session clone directories live under here: _SESSION_BASE / {sid} / {alias} / repo
_SESSION_BASE = _BASE_DIR / "sessions"


def _inject_pat(url: str, pat: str) -> str:
    scheme, rest = url.split("://", 1)
    return f"{scheme}://oauth2:{pat}@{rest}"

def _scrub_pat(text: str, pat: str) -> str:
    return text.replace(pat, "***") if pat and pat in text else text


class ViewerRepoClient:
    """Manages a persistent local clone of one knowledge repo for read-only viewing."""

    def __init__(self, remote_url: str, pat: str = "", branch: str = "main", base_dir: Optional[Path] = None):
        self.remote_url = remote_url
        self.pat = pat
        self.branch = branch
        self.clone_dir = (base_dir or _BASE_DIR) / "repo"
        self._store: Optional[GitStore] = None

    @property
    def configured(self) -> bool:
        return bool(self.remote_url)

    def _auth_url(self) -> str:
        return _inject_pat(self.remote_url, self.pat) if self.pat else self.remote_url

    def ensure_cloned(self) -> None:
        """Clone the repo if not already present; connect the GitStore."""
        if not self.configured:
            return
        if not (self.clone_dir / ".git").exists():
            self.clone_dir.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "--branch", self.branch, self._auth_url(), str(self.clone_dir)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(_scrub_pat(f"Clone failed: {result.stderr.strip()}", self.pat))
        self._store = GitStore(self.clone_dir)

    def reclone(self) -> dict:
        """Delete the local clone and re-clone from scratch. Returns {status, message}."""
        if not self.configured:
            return {"status": "error", "message": "Repo not configured"}
        self._store = None
        shutil.rmtree(self.clone_dir, ignore_errors=True)
        try:
            self.ensure_cloned()
            return {"status": "ok", "message": "Repo recloned."}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def refresh(self) -> dict:
        """Pull latest from remote. Returns {status, commits_behind, message}."""
        if not self.configured:
            return {"status": "error", "message": "Repo not configured"}
        try:
            # Update remote URL with PAT in case it changed
            subprocess.run(
                ["git", "-C", str(self.clone_dir), "remote", "set-url", "origin", self._auth_url()],
                capture_output=True,
            )
            result = subprocess.run(
                ["git", "-C", str(self.clone_dir), "pull", "--rebase", "origin", self.branch],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                return {"status": "error", "message": _scrub_pat(result.stderr.strip(), self.pat)}
            self._store = GitStore(self.clone_dir)
            return {"status": "ok", "message": result.stdout.strip() or "Already up to date."}
        except Exception as exc:
            return {"status": "error", "message": _scrub_pat(str(exc), self.pat)}

    def _require_store(self) -> GitStore:
        if self._store is None:
            raise RuntimeError("Repo not cloned. Call ensure_cloned() first.")
        return self._store

    def list_packages_with_counts(self) -> list[dict]:
        store = self._require_store()
        packages = store.list_packages()
        result = []
        for pkg in packages:
            artifacts = store.list_artifacts(pkg)
            type_counts: dict[str, int] = {}
            for a in artifacts:
                t = a.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            result.append({"name": pkg, "count": len(artifacts), "type_counts": type_counts})
        return result

    def list_artifacts(
        self,
        package: str,
        type_filter: Optional[str] = None,
        name_filter: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self._require_store().list_artifacts(
            package, type_filter=type_filter, name_filter=name_filter, limit=limit
        )

    def list_types(self, package: str) -> list[str]:
        artifacts = self._require_store().list_artifacts(package)
        types = sorted({a.get("type", "unknown") for a in artifacts})
        return types

    def read_artifact(self, package: str, artifact_id: str) -> tuple[str, ArtifactMetadata]:
        store = self._require_store()
        content_str, meta = store.read_content_str(package, artifact_id)
        return content_str, meta

    def get_versions(self, package: str, artifact_id: str) -> list[dict]:
        return self._require_store().get_artifact_versions(artifact_id)

    def search(
        self, package: str, query: str, type_filter: Optional[str] = None
    ) -> list[dict[str, Any]]:
        return self._require_store().search_artifacts(package, query, type_filter=type_filter)

    # ------------------------------------------------------------------
    # Branch switching / workspace rendering
    # ------------------------------------------------------------------

    def list_branches(self) -> list[str]:
        return self._require_store().list_branches()

    def checkout_branch(self, branch_name: str) -> dict:
        """Fetch + checkout a specific branch in the existing clone (no re-clone).

        Runs `git clean -fd` first: instantiating GitStore on a branch lacking a
        committed .index/index.json (e.g. a workspace branch's root, or a plain
        branch with no artifacts yet) creates that file as untracked, which then
        blocks checkout into a branch that *does* track it. The viewer's clone is
        read-only/disposable, so discarding untracked files here is safe.
        """
        fetch = subprocess.run(
            ["git", "-C", str(self.clone_dir), "fetch", "origin", branch_name],
            capture_output=True, text=True,
        )
        if fetch.returncode != 0:
            return {"status": "error", "message": _scrub_pat(fetch.stderr.strip(), self.pat)}
        subprocess.run(["git", "-C", str(self.clone_dir), "clean", "-fd"], capture_output=True, text=True)
        checkout = subprocess.run(
            ["git", "-C", str(self.clone_dir), "checkout", branch_name],
            capture_output=True, text=True,
        )
        if checkout.returncode != 0:
            return {"status": "error", "message": checkout.stderr.strip()}
        self.branch = branch_name
        self._store = GitStore(self.clone_dir)
        return {"status": "ok", "branch": branch_name}

    def read_workspace(self) -> dict:
        """Read index.json + status.json + outputs from the CURRENT branch root.

        Workspace layout is branch-root-relative (index.json/status.json at the repo
        root, packages/ alongside) — not package-scoped like normal artifact browsing.
        """
        import json  # noqa: PLC0415

        root = self.clone_dir
        index_path = root / "index.json"
        status_path = root / "status.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else None
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else None
        return {"index": index, "status": status}
