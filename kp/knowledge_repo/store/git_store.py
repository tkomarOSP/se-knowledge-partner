"""Git-backed artifact store — wraps FilesystemStore and auto-commits on write/delete."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from knowledge_repo.store.filesystem import FilesystemStore
from knowledge_repo.store.indexed_entries import IndexedEntryStore
from knowledge_repo.types.base import BaseArtifact


class GitStore(FilesystemStore):
    """FilesystemStore that commits to git after every write or delete.

    Designed to wrap a cloned GitHub repository (see ``connect_repo`` MCP tool).
    The repo root must already be a git repository; if not, git operations are
    silently skipped so the store degrades gracefully to plain filesystem behaviour.

    The remote URL (with embedded PAT) is read directly from git config so that
    ``push()`` works on a freshly-cloned store without any extra configuration.
    """

    def __init__(self, root: Path | str):
        super().__init__(root)
        self._git_ok = self._check_git()
        self._remote_url = self._read_remote_url()
        self._branch = self._read_current_branch()
        self.entries = IndexedEntryStore(self.root)

    @property
    def branch(self) -> str:
        """Current active branch name."""
        return self._branch

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_git(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _read_remote_url(self) -> Optional[str]:
        """Read the 'origin' remote URL from git config (set automatically after clone)."""
        if not self._git_ok:
            return None
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _read_current_branch(self) -> str:
        """Read the active branch name from git (falls back to 'main')."""
        if not self._git_ok:
            return "main"
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        branch = result.stdout.strip()
        return branch if branch and branch != "HEAD" else "main"

    def list_branches(self) -> list[str]:
        """List all remote branches."""
        if not self._git_ok:
            return []
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        branches = []
        for line in result.stdout.splitlines():
            b = line.strip().removeprefix("origin/")
            if b and not b.startswith("HEAD"):
                branches.append(b)
        return sorted(branches)

    def create_branch(self, name: str, push_upstream: bool = True) -> dict:
        """Create a new branch from HEAD and optionally push it to remote."""
        if not self._git_ok:
            return {"status": "error", "message": "Not a git repository"}
        if not name or name.startswith("-"):
            return {"status": "error", "message": f"Invalid branch name: {name!r}"}
        result = subprocess.run(
            ["git", "checkout", "-b", name],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr.strip()}
        self._branch = name
        if push_upstream:
            push = subprocess.run(
                ["git", "push", "-u", "origin", name],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            if push.returncode != 0:
                return {"status": "created_local_only", "branch": name, "message": push.stderr.strip()}
        return {"status": "ok", "branch": name, "pushed": push_upstream}

    def _git(self, *args: str) -> None:
        if not self._git_ok:
            return
        subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)

    # ------------------------------------------------------------------
    # Write / delete (auto-commit, no auto-push)
    # ------------------------------------------------------------------

    def write(self, artifact: BaseArtifact) -> Path:
        art_dir = super().write(artifact)
        meta = artifact.metadata

        rel = str(art_dir.relative_to(self.root))
        index_rel = str((self.root / ".index").relative_to(self.root))

        self._git("add", rel, index_rel)
        msg = (
            f"artifact: {meta.type}/{meta.name or meta.artifact_id[:8]} "
            f"[{meta.artifact_id[:8]}] in {meta.package_name}"
        )
        self._git("commit", "-m", msg, "--allow-empty")
        return art_dir

    def write_entry(self, package: str, **kwargs) -> dict:
        """Write one indexed entry (observation/decision/lesson_learned/routine_def) and
        git-commit the entry file + the package's index.json together, same pattern as
        write()/delete() above."""
        result = self.entries.write_entry(package, **kwargs)
        entry_path = str((self.root / "packages" / package / result["file_path"]).relative_to(self.root))
        index_path = str((self.root / "packages" / package / "index.json").relative_to(self.root))
        self._git("add", entry_path, index_path)
        msg = f"entry: {result['type']}/{result['title']} [{result['id'][:8]}] in {package}"
        self._git("commit", "-m", msg, "--allow-empty")
        return result

    def delete_entry(self, package: str, entry_id: str) -> None:
        file_path = self.entries.delete_entry(package, entry_id)
        index_path = str((self.root / "packages" / package / "index.json").relative_to(self.root))
        self._git("rm", "-r", "--force", "--ignore-unmatch", f"packages/{package}/{file_path}")
        self._git("add", index_path)
        self._git("commit", "-m", f"entry: delete {entry_id[:8]} from {package}", "--allow-empty")

    def get_entry_versions(self, package: str, entry_id: str) -> list[dict[str, str]]:
        if not self._git_ok:
            return []
        idx = self.entries.load_index(package)
        record = next((e for e in idx["entries"] if e["id"] == entry_id), None)
        if not record:
            return []
        rel_path = f"packages/{package}/{record['file_path']}"
        result = subprocess.run(
            ["git", "log", "--follow", "--format=%H|%ai|%s", "--", rel_path],
            cwd=self.root, capture_output=True, text=True,
        )
        versions = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                versions.append({"commit": parts[0], "timestamp": parts[1], "message": parts[2]})
        return versions

    def delete(self, package_name: str, artifact_id: str) -> None:
        art_dir = self.artifact_dir_path(artifact_id)
        super().delete(package_name, artifact_id)

        index_rel = str((self.root / ".index").relative_to(self.root))
        if art_dir:
            self._git("rm", "-r", "--force", "--ignore-unmatch", str(art_dir.relative_to(self.root)))
        self._git("add", index_rel)
        self._git("commit", "-m", f"artifact: delete {artifact_id[:8]} from {package_name}", "--allow-empty")

    # ------------------------------------------------------------------
    # Explicit push
    # ------------------------------------------------------------------

    def push(self) -> dict:
        """Push committed artifacts to the remote GitHub repository."""
        if not self._git_ok:
            return {"status": "error", "message": "Not a git repository"}
        if not self._remote_url:
            return {"status": "error", "message": "No remote configured — call connect_repo first"}
        result = subprocess.run(
            ["git", "push", "origin", self._branch],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            output = result.stdout.strip() or result.stderr.strip() or "Push successful"
            return {"status": "ok", "message": output}
        return {"status": "error", "message": result.stderr.strip()}

    # ------------------------------------------------------------------
    # Version history
    # ------------------------------------------------------------------

    def get_artifact_versions(self, artifact_id: str) -> list[dict[str, str]]:
        """Return git log entries for the artifact directory."""
        if not self._git_ok:
            return []
        idx = self._load_index()
        entry = idx.get(artifact_id)
        if not entry:
            return []

        result = subprocess.run(
            [
                "git", "log", "--follow", "--format=%H|%ai|%s",
                "--", entry["path"],
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        versions = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                versions.append({"commit": parts[0], "timestamp": parts[1], "message": parts[2]})
        return versions
