# SE Knowledge Partner

An MCP-first toolkit for systems-engineering knowledge work: a git-backed artifact
repository, a prompt library, a routine library, and a read-only web viewer, designed
to be driven by an AI "SE Knowledge Partner" agent (see `docs/`) alongside Capella
model access via a separate `capella-fabric` MCP server.

## Layout

- `kp/knowledge_repo/` — knowledge_repo MCP server: git-backed, indexed-entry store for the 4 Knowledge-layer types (observation, decision, lesson_learned, routine_def)
- `kp/workspace_manager/` — MCP server owning the general typed-artifact system (table, yaml, text, html, arcadia_fabric, session_summary, prompt_def, prompt, json) and per-routine-execution workspace branches
- `kp/project_artifact_repo/` — minimal destination-layer MCP server for promoted workspace outputs (Layer 3: FMEA, Pugh, trade studies); reuses workspace_manager's store/types rather than re-implementing them
- `kp/viewer/` — read-only FastAPI web app for browsing artifacts and workspace branches in a browser (log book timelines, routine viewers, multi-repo sessions, branch switching)
- `kp/prompt_library/` — MCP server for Jinja2 prompt_def templates
- `kp/session_manager/` — MCP server for structured session state
- `kp/kp_agent/` — LangGraph-based agent orchestrator, including the routine execution engine (`routine_engine.py`)
- `docs/SE_Knowledge_Partner_System_Prompt_v3.md` — the system prompt that drives the SE Knowledge Partner agent across these MCP tools

`knowledge_repo`, `workspace_manager`, and `project_artifact_repo` are intentionally
separate MCP servers/sessions — see the knowledge_repo rework decision log for why
(layer separation, and never mixing artifact writes into a repo `capella-fabric`
also manages, which previously caused fast-forward conflicts).

This repo is code-only — it has no `packages/` knowledge-artifact data of its own.
The log book, issue tracking, and routine library live in the original
`knowledge_partner` repo, which `knowledge_repo`'s `clone_knowledge_repo` should
continue to point at.

## Getting started

Each `kp/*` subpackage is independently installable in editable mode:

```bash
pip install -e kp/knowledge_repo -e kp/workspace_manager -e kp/project_artifact_repo \
    -e kp/prompt_library -e kp/session_manager -e kp/kp_agent -e kp/viewer
```

See each subpackage's own docs for running it (e.g. `kp/viewer/deploy/DEPLOY.md`,
`kp/knowledge_repo/deploy/DEPLOY.md` for production deployment).

## Updating the droplet

All services run from the same clone at `/opt/knowledge_partner` on the
Digital Ocean droplet. After pushing new code:

```bash
cd /opt/knowledge_partner
git pull
sudo .venv/bin/pip install -e kp/knowledge_repo -e kp/workspace_manager \
    -e kp/project_artifact_repo -e kp/viewer   # only if dependencies changed
sudo systemctl restart kp-knowledge-repo
sudo systemctl restart kp-workspace-manager
sudo systemctl restart kp-project-artifact-repo
sudo systemctl restart kp-viewer
```

- `kp-knowledge-repo` serves `repo.innovatingwithcapella.com` (port 8002) — knowledge_repo (4 Knowledge types)
- `kp-workspace-manager` serves `workspace.innovatingwithcapella.com` (port 8005) — typed artifacts + workspace branches
- `kp-project-artifact-repo` serves `project-artifacts.innovatingwithcapella.com` (port 8006) — promotion destination, depends on `kp-workspace-manager`
- `kp-viewer` serves `artifacts.innovatingwithcapella.com` (port 8080)

`kp-project-artifact-repo` imports `workspace_manager` directly rather than
vendoring a copy — restart it too if `workspace_manager`'s store/types code
changes. Restarting `kp-viewer` does **not** log out visitors as long as
`KP_VIEWER_SESSION_SECRET` is fixed in `kp-viewer.service` — see
`kp/viewer/deploy/DEPLOY.md` Step 4. Full setup and troubleshooting for each
service lives in its own `deploy/DEPLOY.md`.

## History

This repo was split off from an earlier `knowledge_partner` repo that mixed this
MCP-based architecture with an older, unrelated Jupyter-notebook-based agent
(`se_agent`). This repo starts fresh with only the current MCP-based system.
