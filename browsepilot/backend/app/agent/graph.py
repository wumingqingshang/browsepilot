"""LangGraph StateGraph construction for BrowsePilot agent."""

from langgraph.graph import StateGraph, END

from backend.app.agent.state import AgentState
from backend.app.agent.nodes import (
    plan_node, execute_node, reflect_node, replan_node, answer_node,
)
from backend.app.mcp_client import MCPClient
from backend.app.agent.tools import build_tools_from_mcp


def build_graph(mcp_client: MCPClient):
    """Build and compile the BrowsePilot agent StateGraph."""
    workflow = StateGraph(AgentState)

    # Holder for built tools — None means not yet initialized
    langchain_tools_holder = {"tools": None}

    async def plan(state: AgentState) -> dict:
        return await plan_node(state, mcp_client)

    async def execute(state: AgentState) -> dict:
        if langchain_tools_holder["tools"] is None:
            langchain_tools_holder["tools"] = await build_tools_from_mcp(mcp_client)
        return await execute_node(state, mcp_client, langchain_tools_holder["tools"])

    async def reflect(state: AgentState) -> dict:
        return await reflect_node(state)

    async def replan(state: AgentState) -> dict:
        return await replan_node(state, mcp_client)

    async def answer(state: AgentState) -> dict:
        return await answer_node(state)

    # Add nodes
    workflow.add_node("plan", plan)
    workflow.add_node("execute", execute)
    workflow.add_node("reflect", reflect)
    workflow.add_node("replan", replan)
    workflow.add_node("answer", answer)

    # Set entry
    workflow.set_entry_point("plan")

    # Edges
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "reflect")
    workflow.add_edge("replan", "execute")
    workflow.add_edge("answer", END)

    # Conditional routing from reflect
    workflow.add_conditional_edges(
        "reflect",
        _route_reflect,
        {
            "execute": "execute",
            "replan": "replan",
            "answer": "answer",
        },
    )

    return workflow.compile()


def _route_reflect(state: AgentState) -> str:
    """Route after reflection: retry/continue → execute, replan → replan, done → answer."""
    if state.get("need_replan"):
        return "replan"
    if state.get("plan") and len(state["plan"]) > 0:
        return "execute"
    return "answer"
