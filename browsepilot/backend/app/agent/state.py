"""AgentState definition for the BrowsePilot LangGraph agent."""

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    plan: list[str]
    execution_log: list[dict]
    retry_count: int
    need_replan: bool
    final_answer: str
    token_usage: dict  # {"prompt": int, "completion": int}
