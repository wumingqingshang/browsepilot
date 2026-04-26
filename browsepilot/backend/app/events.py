"""SSE event type definitions for real-time streaming to frontend."""

import json
from typing import Any


class SSEData:
    """Helper to format SSE event dictionaries."""

    @staticmethod
    def plan_generated(steps: list, token_usage: dict) -> dict:
        return {"event": "plan_generated", "data": {"steps": steps, "token_usage": token_usage}}

    @staticmethod
    def step_start(step: str, step_index: int) -> dict:
        return {"event": "step_start", "data": {"step": step, "step_index": step_index}}

    @staticmethod
    def screenshot(base64_data: str, timestamp: str) -> dict:
        return {"event": "screenshot", "data": {"base64": base64_data, "timestamp": timestamp}}

    @staticmethod
    def step_end(step: str, result: dict) -> dict:
        return {"event": "step_end", "data": {"step": step, "result": result}}

    @staticmethod
    def reflection(decision: str, reason: str) -> dict:
        return {"event": "reflection", "data": {"decision": decision, "reason": reason}}

    @staticmethod
    def replan(new_steps: list) -> dict:
        return {"event": "replan", "data": {"new_steps": new_steps}}

    @staticmethod
    def token_update(prompt: int, completion: int) -> dict:
        return {"event": "token_update", "data": {"prompt": prompt, "completion": completion}}

    @staticmethod
    def final_answer(content: str, total_tokens: int) -> dict:
        return {"event": "final_answer", "data": {"content": content, "total_tokens": total_tokens}}

    @staticmethod
    def error(message: str) -> dict:
        return {"event": "error", "data": {"message": message}}
