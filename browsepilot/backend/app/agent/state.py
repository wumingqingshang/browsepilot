"""AgentState definition for the BrowsePilot LangGraph agent."""

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    session_id: str  # for per-session screenshot directories
    intent: str
    plan: list[str]
    execution_log: list[dict]
    degradation_log: list[dict]  # [{"node": "plan", "reason": "json_parse_failed", "timestamp": "..."}]
    retry_count: int
    need_replan: bool
    final_answer: str
    token_usage: dict  # {"prompt": 0, "completion": 0, "breakdown": {"classify": {...}, "plan": {...}, ...}}
    total_steps: int  # Global step counter (never reset), upper limit 20
    plan_step_count: int  # Steps within current plan (reset on replan), upper limit 10
    completion_check_count: int  # max 1 completion check per session
    consecutive_failures: int  # consecutive step failures
    stagnation_count: int  # stagnation detection counter
    replan_count: int  # number of replans in this session
    stagnation_warning: bool  # flag to inject warning into reflect prompt
    stop_reason: str  # reason for forced stop (circuit breaker, step limit, etc.)
    answer_messages: list  # prepared messages for streaming answer generation
