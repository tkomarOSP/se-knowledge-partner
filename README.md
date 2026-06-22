# SE Knowledge Partner

An MCP-first toolkit for systems-engineering knowledge work: a git-backed artifact
repository, a prompt library, a routine library, and a read-only web viewer, designed
to be driven by an AI "SE Knowledge Partner" agent (see `docs/`) alongside Capella
model access via a separate `capella-fabric` MCP server.

## Layout

- `kp/artifact_repo/` — MCP server: git-backed, Pydantic-typed knowledge artifact store (tables, YAML, text, HTML, log books, routine_def, etc.)
- `kp/viewer/` — read-only FastAPI web app for browsing artifacts in a browser (log book timelines, routine viewers, multi-repo sessions)
- `kp/prompt_library/` — MCP server for Jinja2 prompt_def templates
- `kp/session_manager/` — MCP server for structured session state
- `kp/kp_agent/` — LangGraph-based agent orchestrator
- `packages/` — the actual knowledge-artifact data (issue logs, routine definitions) served by `artifact_repo`
- `docs/SE_Knowledge_Partner_System_Prompt_v3.md` — the system prompt that drives the SE Knowledge Partner agent across these MCP tools

## Getting started

Each `kp/*` subpackage is independently installable in editable mode:

```bash
pip install -e kp/artifact_repo -e kp/prompt_library -e kp/session_manager -e kp/kp_agent -e kp/viewer
```

See each subpackage's own docs for running it (e.g. `kp/viewer/deploy/DEPLOY.md`,
`kp/artifact_repo/deploy/DEPLOY.md` for production deployment).

## History

This repo was split off from an earlier `knowledge_partner` repo that mixed this
MCP-based architecture with an older, unrelated Jupyter-notebook-based agent
(`se_agent`). This repo starts fresh with only the current MCP-based system.
