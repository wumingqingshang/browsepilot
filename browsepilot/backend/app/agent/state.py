"""AgentState definition for the BrowsePilot LangGraph agent."""

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    intent: str
    plan: list[str]
    execution_log: list[dict]
    degradation_log: list[dict]  # [{"node": "plan", "reason": "json_parse_failed", "timestamp": "..."}]
    retry_count: int
    need_replan: bool
    final_answer: str
    token_usage: dict  # {"prompt": int, "completion": int}
    completion_check_count: int  # max 1 completion check per session
