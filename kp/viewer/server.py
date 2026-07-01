"""FastAPI web application for viewing KP knowledge artifacts.

Multi-tenant: each browser gets its own session (signed cookie). A session can
hold multiple configured repos (each its own GitHub PAT acting as that repo's
access control) switchable via the nav-bar selector. Sessions are isolated
from each other and idle ones are swept after KP_VIEWER_SESSION_TTL seconds.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from viewer.renderers import (
    badge_class,
    log_entry_from_record,
    parse_entry_md,
    parse_log_book,
    parse_routine_def,
    render_artifact_content,
)
from viewer.repo_client import _SESSION_BASE, ViewerRepoClient

_SESSION_TTL = float(os.environ.get("KP_VIEWER_SESSION_TTL", "86400"))
_SESSION_SECRET = os.environ.get("KP_VIEWER_SESSION_SECRET") or secrets.token_hex(32)

# sid -> {alias: ViewerRepoClient}
_sessions: dict[str, dict[str, ViewerRepoClient]] = {}
# sid -> epoch time of last activity, used by the idle-cleanup sweep
_last_seen: dict[str, float] = {}


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(300)
        now = time.time()
        stale = [sid for sid, ts in _last_seen.items() if now - ts > _SESSION_TTL]
        for sid in stale:
            _sessions.pop(sid, None)
            _last_seen.pop(sid, None)
            shutil.rmtree(_SESSION_BASE / sid, ignore_errors=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="KP Artifact Viewer", docs_url=None, redoc_url=None, lifespan=_lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    session_cookie="kp_viewer_session",
    max_age=int(_SESSION_TTL),
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["badge_class"] = badge_class


def _date_filter(value) -> str:
    """Format a datetime or ISO string as YYYY-MM-DD."""
    if value is None:
        return "–"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


templates.env.filters["date"] = _date_filter


# ---------------------------------------------------------------------------
# Session / multi-repo helpers
# ---------------------------------------------------------------------------

def _get_sid(request: Request, create: bool = False) -> Optional[str]:
    sid = request.session.get("sid")
    if not sid and create:
        sid = uuid.uuid4().hex
        request.session["sid"] = sid
    return sid


def _get_repos(request: Request) -> dict[str, ViewerRepoClient]:
    sid = request.session.get("sid")
    if not sid:
        return {}
    _last_seen[sid] = time.time()
    return _sessions.get(sid, {})


def _get_active_client(request: Request) -> Optional[ViewerRepoClient]:
    repos = _get_repos(request)
    if not repos:
        return None
    alias = request.session.get("active_alias")
    if alias not in repos:
        alias = next(iter(repos))
        request.session["active_alias"] = alias
    return repos[alias]


def _derive_alias(repo_url: str, existing: set[str]) -> str:
    base = repo_url.rstrip("/").rsplit("/", 1)[-1]
    base = base.removesuffix(".git") or "repo"
    alias = base
    i = 2
    while alias in existing:
        alias = f"{base}-{i}"
        i += 1
    return alias


def _render(request: Request, name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    client = _get_active_client(request)
    try:
        nav_branches = client.list_branches() if client else []
    except Exception:
        nav_branches = []
    context = {
        **context,
        "nav_repos": _get_repos(request),
        "active_alias": request.session.get("active_alias"),
        "nav_branches": nav_branches,
        "active_branch": client.branch if client else None,
    }
    return templates.TemplateResponse(request, name, context, status_code=status_code)


# ---------------------------------------------------------------------------
# Routes — specific paths before wildcard
# ---------------------------------------------------------------------------

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    client = _get_active_client(request)
    if client is None:
        return RedirectResponse(url="/setup", status_code=303)
    try:
        packages = client.list_packages_with_counts()
    except Exception as exc:
        return _render(request, "index.html", {"packages": [], "error": str(exc)})
    return _render(request, "index.html", {"packages": packages, "error": None})


@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    return _render(request, "setup.html", {"error": None, "repo_url": "", "branch": "main"})


@app.post("/setup", response_class=HTMLResponse)
async def setup_post(
    request: Request,
    repo_url: str = Form(...),
    pat: str = Form(""),
    branch: str = Form("main"),
):
    repo_url = repo_url.strip().rstrip("/")
    pat = pat.strip()
    branch = branch.strip() or "main"

    if not repo_url:
        return _render(request, "setup.html", {
            "error": "Repository URL is required.", "repo_url": repo_url, "branch": branch,
        })

    sid = _get_sid(request, create=True)
    repos = _sessions.setdefault(sid, {})
    alias = _derive_alias(repo_url, set(repos.keys()))

    client = ViewerRepoClient(repo_url, pat, branch, base_dir=_SESSION_BASE / sid / alias)
    try:
        client.ensure_cloned()
    except Exception as exc:
        return _render(request, "setup.html", {
            "error": str(exc), "repo_url": repo_url, "branch": branch,
        })

    repos[alias] = client
    _last_seen[sid] = time.time()
    request.session["active_alias"] = alias
    return RedirectResponse(url="/", status_code=303)


@app.post("/switch-repo")
async def switch_repo(request: Request, alias: str = Form(...)):
    repos = _get_repos(request)
    if alias in repos:
        request.session["active_alias"] = alias
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


@app.post("/remove-repo")
async def remove_repo(request: Request, alias: str = Form(...)):
    sid = request.session.get("sid")
    repos = _sessions.get(sid, {}) if sid else {}
    if alias in repos:
        client = repos.pop(alias)
        shutil.rmtree(client.clone_dir.parent, ignore_errors=True)
        if request.session.get("active_alias") == alias:
            remaining = list(repos.keys())
            if remaining:
                request.session["active_alias"] = remaining[0]
            else:
                request.session.pop("active_alias", None)
    if repos:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/setup", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    sid = request.session.get("sid")
    if sid:
        _sessions.pop(sid, None)
        _last_seen.pop(sid, None)
        shutil.rmtree(_SESSION_BASE / sid, ignore_errors=True)
    request.session.clear()
    return RedirectResponse(url="/setup", status_code=303)


@app.post("/refresh")
async def refresh(request: Request):
    client = _get_active_client(request)
    if client:
        client.refresh()
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


@app.post("/reclone")
async def reclone(request: Request):
    client = _get_active_client(request)
    if client:
        client.reclone()
    return RedirectResponse(url="/", status_code=303)


@app.post("/switch-branch")
async def switch_branch(request: Request, branch: str = Form(...)):
    client = _get_active_client(request)
    if client:
        client.checkout_branch(branch)
    referer = request.headers.get("referer", "/")
    return RedirectResponse(url=referer, status_code=303)


@app.get("/workspace/{branch_name:path}", response_class=HTMLResponse)
async def workspace_view(request: Request, branch_name: str):
    client = _get_active_client(request)
    if client is None:
        return RedirectResponse(url="/setup", status_code=303)
    checkout = client.checkout_branch(branch_name)
    if checkout.get("status") != "ok":
        return HTMLResponse(f"<h1>Error</h1><p>{checkout.get('message')}</p>", status_code=404)
    ws = client.read_workspace()
    return _render(request, "workspace.html", {"branch_name": branch_name, "workspace": ws})


@app.get("/{package}", response_class=HTMLResponse)
async def package_view(
    request: Request,
    package: str,
    type: Optional[str] = None,
    q: Optional[str] = None,
):
    client = _get_active_client(request)
    if client is None:
        return RedirectResponse(url="/setup", status_code=303)
    if q:
        artifacts = client.search(package, q, type_filter=type)
    else:
        artifacts = client.list_artifacts(package, type_filter=type)
    types = client.list_types(package)
    return _render(request, "package.html", {
        "package": package,
        "artifacts": artifacts,
        "types": types,
        "type_filter": type,
        "q": q or "",
    })


@app.get("/{package}/log", response_class=HTMLResponse)
async def log_view(request: Request, package: str, filter_type: Optional[str] = None):
    """Chronological view over observation/decision/lesson_learned/note entries —
    newest first. Reads each entry's own file directly (rather than assembling
    all entries into one Markdown blob and re-splitting on '---'), so a '---'
    horizontal rule inside an entry's body can't be mistaken for an entry
    boundary and truncate it. Replaces the old monolithic log_book artifact."""
    client = _get_active_client(request)
    if client is None:
        return RedirectResponse(url="/setup", status_code=303)
    try:
        records = client.list_entries(package)
    except Exception as exc:
        return HTMLResponse(f"<h1>Error</h1><p>{exc}</p>", status_code=404)

    type_counts: dict[str, int] = {}
    for r in records:
        type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1

    shown = [r for r in records if not filter_type or r["type"] == filter_type]
    entries = []
    for seq, record in enumerate(shown, start=1):
        full_md, _ = client.read_entry(package, record["id"])
        entries.append(log_entry_from_record(record, full_md, sequence=seq))
    entries.sort(key=lambda e: (e.timestamp, e.sequence), reverse=True)

    return _render(request, "log.html", {
        "package": package,
        "entries": entries,
        "type_counts": type_counts,
        "filter_type": filter_type or "",
    })


@app.get("/{package}/{artifact_id}/versions", response_class=HTMLResponse)
async def versions_view(request: Request, package: str, artifact_id: str):
    client = _get_active_client(request)
    if client is None:
        return RedirectResponse(url="/setup", status_code=303)
    try:
        _, meta = client.read_artifact(package, artifact_id)
        versions = client.get_versions(package, artifact_id)
        name = meta.name
    except Exception:
        try:
            _, record = client.read_entry(package, artifact_id)
            versions = client.get_entry_versions(package, artifact_id)
            name = record["title"]
        except Exception:
            return _render(request, "not_found.html", {
                "package": package,
                "artifact_id": artifact_id,
            }, status_code=404)
    return _render(request, "versions.html", {
        "package": package,
        "artifact_id": artifact_id,
        "name": name,
        "versions": versions,
    })


@app.get("/{package}/{artifact_id}", response_class=HTMLResponse)
async def artifact_view(
    request: Request,
    package: str,
    artifact_id: str,
    filter_type: Optional[str] = None,
):
    client = _get_active_client(request)
    if client is None:
        return RedirectResponse(url="/setup", status_code=303)
    try:
        content_str, meta = client.read_artifact(package, artifact_id)
    except Exception:
        try:
            full_md, record = client.read_entry(package, artifact_id)
        except Exception:
            return _render(request, "not_found.html", {
                "package": package,
                "artifact_id": artifact_id,
            }, status_code=404)
        author, body_html = parse_entry_md(full_md)
        return _render(request, "entry.html", {
            "package": package,
            "record": record,
            "author": author,
            "body_html": body_html,
        })

    if meta.type == "log_book":
        header_html, entries, type_counts = parse_log_book(content_str, filter_type=filter_type)
        return _render(request, "logbook.html", {
            "package": package,
            "meta": meta,
            "header_html": header_html,
            "entries": entries,
            "type_counts": type_counts,
            "filter_type": filter_type or "",
        })

    if meta.type == "routine_def":
        routine = parse_routine_def(content_str)
        return _render(request, "routine.html", {
            "package": package,
            "meta": meta,
            "routine": routine,
        })

    content_html = render_artifact_content(content_str, meta.type)
    return _render(request, "artifact.html", {
        "package": package,
        "meta": meta,
        "content_html": content_html,
    })
