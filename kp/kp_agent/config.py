"""Configuration for KP Agent — MCP server URLs and OpenAI settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# MCP server registry
# ---------------------------------------------------------------------------

MCP_SERVERS: dict[str, str] = {
    "artifact_repo":   os.environ.get("KP_ARTIFACT_REPO_URL",   "https://repo.innovatingwithcapella.com/mcp"),
    "prompt_library":  os.environ.get("KP_PROMPT_LIBRARY_URL",  "http://localhost:8003/mcp"),
    "session_manager": os.environ.get("KP_SESSION_MANAGER_URL", "http://localhost:8004/mcp"),
    "capella_fabric":  os.environ.get("KP_CAPELLA_FABRIC_URL",  "https://mcp.innovatingwithcapella.com/mcp"),
}


# ---------------------------------------------------------------------------
# OpenAI / LLM config
# ---------------------------------------------------------------------------

def _load_secrets(name: str) -> dict:
    path = Path.home() / ".secrets" / name
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_openai_config(profile: Optional[str] = None) -> dict:
    """Return OpenAI client kwargs from ~/.secrets/model_configs.json or env vars."""
    configs = _load_secrets("model_configs.json")
    cfg = configs.get(profile or "_default", configs.get("_default", {}))
    return {
        "api_key":  cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", ""),
        "base_url": cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL"),
        "model":    cfg.get("model") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    }
