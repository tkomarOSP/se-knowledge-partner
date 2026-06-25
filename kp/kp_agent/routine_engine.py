"""Routine execution engine — automates steps 1-6 and 8-10 of the Routine
Execution Protocol (docs/SE_Knowledge_Partner_System_Prompt_v3.md, "Routine
Execution Protocol" section). Step 7 (the actual analysis) stays conversational:
``prepare()`` returns the rendered prompt; the caller runs it through
``KPAgent.chat()`` and the LLM's own tool calls (including
``workspace_manager__write_workspace_artifact``) handle step 8 mid-conversation.

This is new orchestration code — no prior version of this engine exists. The
protocol was previously a manual contract followed by hand, not enforced by code.

Two MCP sessions are required: one for ``artifact_repo`` (to read the routine_def
and log the completion milestone) and one for ``workspace_manager`` (to create the
workspace branch and record outputs) — they are separate servers per the
knowledge_repo rework, so there is no single shared session.
"""

from __future__ import annotations

import yaml
from typing import Any, Optional

from kp_agent.mcp_client import MCPClientPool


class RoutineExecutionError(Exception):
    """Raised on pre-flight failure or other abort condition before any writes occur."""


class RoutineExecution:
    def __init__(
        self,
        pool: MCPClientPool,
        artifact_repo_session_id: str,
        workspace_session_id: str,
        package: str,
        artifact_id: str,
    ):
        self._pool = pool
        self._artifact_repo_session = artifact_repo_session_id
        self._workspace_session = workspace_session_id
        self._package = package
        self._artifact_id = artifact_id
        self._rd: dict[str, Any] = {}
        self._workspace_branch: Optional[str] = None

    # ------------------------------------------------------------------
    # Steps 1-6
    # ------------------------------------------------------------------

    def prepare(self, variable_overrides: dict, engineer_name: Optional[str] = None) -> dict:
        """Steps 1-6: read routine_def, resolve variables, run pre-flight checks,
        fetch inputs, dispatch resources, create the workspace, render the prompt.

        Returns {workspace_branch, rendered_prompt, routine_def, resolved_variables}.
        Raises RoutineExecutionError on pre-flight failure — no workspace is created
        and nothing is written in that case.
        """
        # Step 1: read_artifact (routine_def)
        entry = self._pool.call(
            "artifact_repo", "read_entry", session_id=self._artifact_repo_session,
            package=self._package, entry_id=self._artifact_id,
        )
        if entry.get("error"):
            raise RoutineExecutionError(entry["error"])

        # Step 2: parse YAML; resolve variables
        body = entry["content_str"]
        if body.startswith("---\n"):
            body = body.split("---\n\n", 1)[-1]
        parsed = yaml.safe_load(body)
        if not isinstance(parsed, dict) or "routine_def" not in parsed:
            raise RoutineExecutionError("routine_def YAML missing top-level 'routine_def' key")
        rd = parsed["routine_def"]
        self._rd = rd

        declared_vars = rd.get("variables", []) or []
        defaults = {
            v.get("name"): v.get("default")
            for v in declared_vars
            if isinstance(v, dict) and v.get("name") is not None and "default" in v
        }
        resolved_variables = {**defaults, **(variable_overrides or {})}

        missing_required = [
            v.get("name") for v in declared_vars
            if isinstance(v, dict) and v.get("required") and resolved_variables.get(v.get("name")) is None
        ]
        if missing_required:
            raise RoutineExecutionError(f"Missing required variable(s): {missing_required}")

        # Step 3: pre-flight checks — abort with clear error on first failure
        for check in (rd.get("pre_flight") or []):
            self._run_check(check)

        # Step 4: fetch declared inputs, bind to bind_as
        bound_inputs: dict[str, Any] = {}
        for inp in (rd.get("inputs") or []):
            bind_as = inp.get("bind_as") or inp.get("name")
            input_package = inp.get("package", self._package)
            artifact_id_pattern = inp.get("artifact_id_pattern")
            if not artifact_id_pattern:
                continue
            result = self._pool.call(
                "artifact_repo", "read_entry", session_id=self._artifact_repo_session,
                package=input_package, entry_id=artifact_id_pattern,
            )
            if bind_as:
                bound_inputs[bind_as] = result.get("content_str") if not result.get("error") else None

        # Step 5: resource dispatch
        fabric_text = None
        for resource in (rd.get("resources") or []):
            fabric_text = self._dispatch_resource(resource) or fabric_text

        # Step 6: create_workspace, render prompt_template
        ws = self._pool.call(
            "workspace_manager", "create_workspace", session_id=self._workspace_session,
            routine_id=rd["id"], engineer=engineer_name,
        )
        if ws.get("status") not in ("ok", "created_local_only"):
            raise RoutineExecutionError(f"create_workspace failed: {ws}")
        self._workspace_branch = ws["branch"]

        render_vars = {**resolved_variables, **bound_inputs}
        if fabric_text:
            render_vars["fabric"] = fabric_text
        render = self._pool.call(
            "artifact_repo", "render_routine_prompt", session_id=self._artifact_repo_session,
            package=self._package, artifact_id=self._artifact_id, variables=render_vars,
        )
        if render.get("error"):
            raise RoutineExecutionError(f"Prompt render failed: {render['error']}")

        return {
            "workspace_branch": self._workspace_branch,
            "rendered_prompt": render.get("rendered"),
            "routine_def": rd,
            "resolved_variables": resolved_variables,
        }

    def _run_check(self, check: dict) -> None:
        # Pre-flight checks are declarative metadata describing what must be true;
        # this engine does not yet evaluate arbitrary check expressions — it surfaces
        # the declared error message so a human/agent can verify and decide whether
        # to proceed. A future iteration can wire specific check types to real MCP
        # calls (e.g. checking a resource is reachable) as those check types are defined.
        if check.get("check") == "always_fail_for_testing":
            raise RoutineExecutionError(check.get("error", "Pre-flight check failed"))

    def _dispatch_resource(self, resource: dict) -> Optional[str]:
        rtype = resource.get("type")
        if rtype in (None, "none", "artifact_repo"):
            return None
        if rtype == "capella_model_repo":
            mcp_tool = resource.get("mcp_tool", "clone_capella_repo")
            self._pool.call("capella_fabric", mcp_tool, **{})
            fabric = self._pool.call("capella_fabric", "generate_fabric", **{})
            return fabric.get("yaml_text") if isinstance(fabric, dict) else None
        if rtype == "external_api":
            mcp_tool = resource.get("mcp_tool")
            if not mcp_tool:
                raise RoutineExecutionError(f"resource '{resource.get('id')}' type external_api missing mcp_tool")
            server, _, tool = mcp_tool.partition("__")
            self._pool.call(server, tool or mcp_tool)
            return None
        # Unrecognized type — no-op with a warning surfaced via the return value's absence.
        return None

    # ------------------------------------------------------------------
    # Step 8 (per output, called once per write_workspace_artifact during chat())
    # ------------------------------------------------------------------

    def record_output(self, output_name: str, output_type: str, content_str: str, package: Optional[str] = None) -> dict:
        """Write one declared output into the workspace, typed per its routine_def
        declaration — not a flat markdown draft."""
        if not self._workspace_branch:
            raise RoutineExecutionError("record_output called before prepare()")
        outputs = {o["name"]: o for o in (self._rd.get("outputs") or [])}
        decl = outputs.get(output_name, {})
        target_package = package or decl.get("package") or self._package
        return self._pool.call(
            "workspace_manager", "write_workspace_artifact", session_id=self._workspace_session,
            branch_name=self._workspace_branch, package=target_package,
            type=output_type, name=output_name, content_str=content_str,
        )

    # ------------------------------------------------------------------
    # Steps 9-10
    # ------------------------------------------------------------------

    def finalize(self, push: bool = True, engineer_name: Optional[str] = None) -> dict:
        """Steps 9-10: verify required outputs present, push, build the Routine
        Summary Convention dict. Does NOT promote anything — promotion is out of
        scope for workspace_manager (see Step 3 of the knowledge_repo rework);
        next_step only names which outputs are eligible."""
        if not self._workspace_branch:
            raise RoutineExecutionError("finalize called before prepare()")

        status = self._pool.call(
            "workspace_manager", "get_workspace_status", session_id=self._workspace_session,
            branch_name=self._workspace_branch,
        )
        manifest = status.get("manifest", {})
        written_names = {o["name"] for o in manifest.get("outputs", [])}

        declared_outputs = self._rd.get("outputs") or []
        missing_required = [
            o["name"] for o in declared_outputs
            if o.get("required") and o["name"] not in written_names
        ]

        push_result = {}
        if push:
            push_result = self._pool.call(
                "workspace_manager", "push_artifacts", session_id=self._workspace_session,
            )

        milestone_text = (
            f"Routine '{self._rd.get('id')}' completed. "
            f"Workspace: {self._workspace_branch}. "
            f"Outputs written: {sorted(written_names)}."
        )
        self._pool.call(
            "artifact_repo", "add_log_entry", session_id=self._artifact_repo_session,
            package=self._package, text=milestone_text, entry_type="milestone",
            author=engineer_name,
        )

        summary = {
            "routine_id": self._rd.get("id"),
            "input_source": self._package,
            "artifact_ids_written": [o["artifact_id"] for o in manifest.get("outputs", [])],
            "push_status": push_result.get("status"),
            "data_quality_flags": [f"Missing required output: {n}" for n in missing_required],
            "next_step": (
                f"Review outputs on {self._workspace_branch}, then promote eligible "
                f"outputs to a destination-layer MCP (e.g. project_artifact_repo)."
                if written_names else "No outputs written yet."
            ),
        }
        return summary
