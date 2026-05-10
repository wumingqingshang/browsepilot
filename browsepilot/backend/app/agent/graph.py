"""LangGraph StateGraph construction for BrowsePilot agent."""

from langgraph.graph import StateGraph, END

from backend.app.agent.state import AgentState
from backend.app.agent.nodes import (
    plan_node, execute_node, reflect_node, replan_node, answer_node,
    classify_node,
)
from backend.app.mcp_client import MCPClient
from backend.app.agent.tools import build_tools_from_mcp


def build_graph(mcp_client: MCPClient, lazy_mcp: bool = False):
    """Build and compile the BrowsePilot agent StateGraph."""
    workflow = StateGraph(AgentState)

    langchain_tools_holder = {"tools": None}

    async def classify(state: AgentState) -> dict:
        return await classify_node(state)

    async def plan(state: AgentState) -> dict:
        # Lazy MCP connect: only connect when browser_task reaches plan
        if lazy_mcp and not mcp_client.is_connected:
            await mcp_client.connect()
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
    workflow.add_node("classify", classify)
    workflow.add_node("plan", plan)
    workflow.add_node("execute", execute)
    workflow.add_node("reflect", reflect)
    workflow.add_node("replan", replan)
    workflow.add_node("answer", answer)

    # Entry: classify instead of plan
    workflow.set_entry_point("classify")

    # classify → conditional routing
    workflow.add_conditional_edges(
        "classify",
        _route_classify,
        {
            "chitchat": "answer",
            "knowledge_qa": "answer",
            "browser_task": "plan",
        },
    )

    # Rest of edges unchanged
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "reflect")
    workflow.add_edge("replan", "execute")
    workflow.add_edge("answer", END)

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


def _route_classify(state: AgentState) -> str:
    """Route after classification: chitchat/knowledge_qa → answer, browser_task → plan."""
    intent = state.get("intent", "browser_task")
    if intent in ("chitchat", "knowledge_qa"):
        return intent
    return "browser_task"


def _route_reflect(state: AgentState) -> str:
    """Route after reflection: retry/continue → execute, replan → replan, done → answer."""
    if state.get("need_replan"):
        return "replan"
    if state.get("plan") and len(state["plan"]) > 0:
        return "execute"
    return "answer"
