"""Knowledge Partner Agent — LangGraph StateGraph backed by KP MCP servers.

Usage::

    from kp_agent.agent import KPAgent

    agent = KPAgent()
    response = agent.chat("List available artifact packages")
    print(response)
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from openai import OpenAI
from typing_extensions import TypedDict

from kp_agent.config import MCP_SERVERS, get_openai_config
from kp_agent.mcp_client import MCPClientPool
from kp_agent.routine_engine import RoutineExecution


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# KPAgent
# ---------------------------------------------------------------------------

class KPAgent:
    """Thin LangGraph agent that exposes all KP MCP server tools to an LLM.

    The agent discovers available tools at construction time by querying
    each registered MCP server.  Tool calls are routed back to the
    appropriate server via MCPClientPool.
    """

    def __init__(
        self,
        servers: dict[str, str] | None = None,
        openai_profile: str | None = None,
        system_prompt: str | None = None,
    ):
        cfg = get_openai_config(openai_profile)
        self._model = cfg.pop("model")
        self._client = OpenAI(**{k: v for k, v in cfg.items() if v})
        self._pool = MCPClientPool(servers or MCP_SERVERS)
        self._system = system_prompt or (
            "You are a Knowledge Partner agent. "
            "You help users store, retrieve, and reason over structured artifacts "
            "using the available MCP tools. "
            "Always confirm artifact IDs when writing so users can retrieve them later."
        )
        self._tools_schema = self._build_tools_schema()
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Tool schema discovery
    # ------------------------------------------------------------------

    def _build_tools_schema(self) -> list[dict[str, Any]]:
        """Query each MCP server and convert tool manifests to OpenAI tool format."""
        openai_tools = []
        for server_name, url in self._pool._servers.items():
            try:
                tools = self._pool.list_tools(server_name)
            except Exception as exc:
                print(f"[kp_agent] Warning: could not reach {server_name} ({url}): {exc}")
                continue
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": f"{server_name}__{tool['name']}",
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                    },
                })
        return openai_tools

    # ------------------------------------------------------------------
    # LangGraph graph
    # ------------------------------------------------------------------

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("llm", self._llm_node)
        graph.add_node("tools", self._tools_node)
        graph.set_entry_point("llm")
        graph.add_conditional_edges("llm", self._should_continue, {"tools": "tools", "end": END})
        graph.add_edge("tools", "llm")
        return graph.compile()

    def _llm_node(self, state: AgentState) -> AgentState:
        messages = state["messages"]
        system = [{"role": "system", "content": self._system}]
        response = self._client.chat.completions.create(
            model=self._model,
            messages=system + messages,
            tools=self._tools_schema or None,
            tool_choice="auto" if self._tools_schema else None,
        )
        msg = response.choices[0].message
        return {"messages": [msg]}

    def _tools_node(self, state: AgentState) -> AgentState:
        last = state["messages"][-1]
        results = []
        for tc in (last.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments)
                result = self._pool.call_by_prefixed_name(tc.function.name, **args)
            except Exception as exc:
                result = {"error": str(exc)}
            results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })
        return {"messages": results}

    @staticmethod
    def _should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "end"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def chat(self, user_message: str) -> str:
        """Send a message and return the agent's final text response."""
        final = self._graph.invoke({"messages": [{"role": "user", "content": user_message}]})
        last = final["messages"][-1]
        return last.content if hasattr(last, "content") else str(last)

    def run_routine(
        self,
        package: str,
        artifact_id: str,
        variables: dict,
        knowledge_repo_session_id: str,
        workspace_session_id: str,
        engineer_name: str | None = None,
    ) -> dict:
        """Drive a routine_def end-to-end: steps 1-6 (prepare) automated, step 7
        (analysis) via the existing chat() path — the LLM's own tool calls during
        that turn (including workspace_manager__write_workspace_artifact) carry out
        step 8 — then steps 9-10 (finalize) automated.

        Both session_ids must already exist (clone_knowledge_repo on knowledge_repo,
        create_workspace_session on workspace_manager) — this method does not manage
        session lifecycle itself, since the two are separate MCP servers.
        """
        execution = RoutineExecution(
            self._pool, knowledge_repo_session_id, workspace_session_id, package, artifact_id,
        )
        prep = execution.prepare(variables, engineer_name)
        self.chat(prep["rendered_prompt"])
        return execution.finalize(engineer_name=engineer_name)

    def stream(self, user_message: str):
        """Yield messages as the graph executes (for notebook/UI use)."""
        for event in self._graph.stream(
            {"messages": [{"role": "user", "content": user_message}]},
            stream_mode="values",
        ):
            yield event["messages"][-1]
