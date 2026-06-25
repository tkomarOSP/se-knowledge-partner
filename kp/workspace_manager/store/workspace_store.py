"""Branch-scoped workspace lifecycle on top of GitStore.

A workspace is a git branch (``workspace/{routine_id}-{date}``) holding:
- index.json   — manifest + execution status reference (routine_id, branch, engineer, outputs[])
- status.json  — {status: running|paused|complete|promoted, updated_at, message}
- packages/{package}/artifacts/...   — typed artifacts, same layout GitStore already writes

Workspace outputs are real typed artifacts (table/yaml/json/etc, written via the
ported GitStore.write()), not flat markdown drafts — routine_def output
declarations name one of these types and get a properly validated artifact.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from workspace_manager.store.git_store import GitStore
from workspace_manager.types.base import ArtifactMetadata
from workspace_manager.types.registry import get_artifact_class


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class WorkspaceStore:
    """Wraps a GitStore (one clone, one session) and manages workspace branches in it."""

    def __init__(self, git_store: GitStore):
        self.store = git_store

    # ------------------------------------------------------------------
    # Manifest I/O (branch-root-relative, not package-scoped)
    # ------------------------------------------------------------------

    def _index_path(self) -> Path:
        return self.store.root / "index.json"

    def _status_path(self) -> Path:
        return self.store.root / "status.json"

    def _load_index(self) -> dict[str, Any]:
        p = self._index_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _save_index(self, idx: dict[str, Any]) -> None:
        self._index_path().write_text(json.dumps(idx, indent=2, default=str), encoding="utf-8")

    def _load_status(self) -> dict[str, Any]:
        p = self._status_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _save_status(self, status: dict[str, Any]) -> None:
        self._status_path().write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, routine_id: str, engineer: Optional[str] = None) -> dict[str, Any]:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        branch = f"workspace/{routine_id}-{date}"
        result = self.store.create_branch(branch, push_upstream=True)
        if result.get("status") not in ("ok", "created_local_only"):
            return result

        manifest = {
            "routine_id": routine_id,
            "branch": branch,
            "created_at": _utcnow_iso(),
            "engineer": engineer,
            "outputs": [],
        }
        status = {"status": "running", "updated_at": _utcnow_iso(), "message": None}
        self._save_index(manifest)
        self._save_status(status)

        self.store._git("add", "index.json", "status.json")
        self.store._git("commit", "-m", f"workspace: create {branch}", "--allow-empty")
        push = subprocess.run(
            ["git", "push", "origin", branch], cwd=self.store.root, capture_output=True, text=True,
        )
        return {"status": "ok", "branch": branch, "pushed": push.returncode == 0}

    # ------------------------------------------------------------------
    # Write / read workspace artifacts
    # ------------------------------------------------------------------

    def write_workspace_artifact(
        self,
        branch_name: str,
        package: str,
        type: str,
        name: str,
        content_str: str,
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Checkout the workspace branch, write a typed artifact via GitStore.write()
        (reuses the existing typed-artifact path verbatim), append a manifest record,
        and commit both together."""
        if self.store.branch != branch_name:
            checkout = self.store.checkout_branch(branch_name)
            if checkout.get("status") != "ok":
                return checkout

        cls = get_artifact_class(type)
        try:
            content = cls.deserialize_content(content_str)
        except Exception as exc:
            return {"error": f"Content validation failed for type '{type}': {exc}"}

        meta = ArtifactMetadata(type=type, name=name, package_name=package, tags=tags or [])
        artifact = cls(metadata=meta, content=content)
        art_dir = self.store.write(artifact)  # already commits artifact + .index/index.json

        manifest = self._load_index()
        manifest.setdefault("outputs", []).append({
            "name": name,
            "type": type,
            "artifact_id": meta.artifact_id,
            "package": package,
            "written_at": _utcnow_iso(),
        })
        self._save_index(manifest)
        self.store._git("add", "index.json")
        self.store._git("commit", "-m", f"workspace: record output {name} ({type})", "--allow-empty")

        return {"artifact_id": meta.artifact_id, "path": str(art_dir), "type": type, "name": name}

    def read_workspace_artifact(self, branch_name: str, output_name: str) -> dict[str, Any]:
        """Read an output's content via `git show branch:path` — no checkout needed,
        so this never disrupts the session's current branch."""
        manifest = self._read_manifest_on_branch(branch_name)
        if "error" in manifest:
            return manifest
        record = next((o for o in manifest.get("outputs", []) if o["name"] == output_name), None)
        if not record:
            return {"error": f"Output '{output_name}' not found on branch '{branch_name}'"}

        idx = self._read_artifact_index_on_branch(branch_name)
        art_entry = idx.get(record["artifact_id"])
        if not art_entry:
            return {"error": f"Artifact '{record['artifact_id']}' not found in branch index"}

        path_prefix = art_entry["path"]
        # Find the content file name via git ls-tree (extension is type-dependent)
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", f"{branch_name}", f"{path_prefix}/"],
            cwd=self.store.root, capture_output=True, text=True,
        )
        content_file = next((f for f in ls.stdout.splitlines() if "/content." in f), None)
        if not content_file:
            return {"error": f"No content file found for artifact at {path_prefix}"}

        show = subprocess.run(
            ["git", "show", f"{branch_name}:{content_file}"],
            cwd=self.store.root, capture_output=True, text=True,
        )
        if show.returncode != 0:
            return {"error": show.stderr.strip()}

        return {
            "content_str": show.stdout,
            "type": record["type"],
            "metadata": {"artifact_id": record["artifact_id"], "package": record["package"], "name": record["name"]},
        }

    def _read_manifest_on_branch(self, branch_name: str) -> dict[str, Any]:
        show = subprocess.run(
            ["git", "show", f"{branch_name}:index.json"],
            cwd=self.store.root, capture_output=True, text=True,
        )
        if show.returncode != 0:
            return {"error": show.stderr.strip()}
        return json.loads(show.stdout)

    def _read_artifact_index_on_branch(self, branch_name: str) -> dict[str, Any]:
        show = subprocess.run(
            ["git", "show", f"{branch_name}:.index/index.json"],
            cwd=self.store.root, capture_output=True, text=True,
        )
        if show.returncode != 0:
            return {}
        return json.loads(show.stdout)

    # ------------------------------------------------------------------
    # List / status / close
    # ------------------------------------------------------------------

    def list_workspaces(self) -> list[dict[str, Any]]:
        result = subprocess.run(
            ["git", "branch", "-a", "--format=%(refname:short)"],
            cwd=self.store.root, capture_output=True, text=True,
        )
        branches = sorted({
            b.strip().removeprefix("origin/")
            for b in result.stdout.splitlines()
            if "workspace/" in b
        })
        out = []
        for b in branches:
            manifest = self._read_manifest_on_branch(b)
            status_raw = subprocess.run(
                ["git", "show", f"{b}:status.json"], cwd=self.store.root, capture_output=True, text=True,
            )
            status = json.loads(status_raw.stdout) if status_raw.returncode == 0 else {}
            out.append({"branch": b, "manifest": manifest, "status": status})
        return out

    def get_status(self, branch_name: str) -> dict[str, Any]:
        status_raw = subprocess.run(
            ["git", "show", f"{branch_name}:status.json"], cwd=self.store.root, capture_output=True, text=True,
        )
        if status_raw.returncode != 0:
            return {"error": status_raw.stderr.strip()}
        manifest = self._read_manifest_on_branch(branch_name)
        return {"branch": branch_name, "status": json.loads(status_raw.stdout), "manifest": manifest}

    def close(self, branch_name: str) -> dict[str, Any]:
        """Set status.json status='complete'. Does NOT touch the git branch itself —
        it is left untouched on the remote indefinitely (no rename, no delete)."""
        if self.store.branch != branch_name:
            checkout = self.store.checkout_branch(branch_name)
            if checkout.get("status") != "ok":
                return checkout

        status = self._load_status()
        status["status"] = "complete"
        status["updated_at"] = _utcnow_iso()
        self._save_status(status)
        self.store._git("add", "status.json")
        self.store._git("commit", "-m", f"workspace: close {branch_name}", "--allow-empty")
        push = subprocess.run(
            ["git", "push", "origin", branch_name], cwd=self.store.root, capture_output=True, text=True,
        )
        return {"status": "ok", "branch": branch_name, "pushed": push.returncode == 0}
