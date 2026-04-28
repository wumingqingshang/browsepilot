"""FastAPI application entry point with SSE streaming task execution."""

import uuid
import json
import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from loguru import logger
import sys

from backend.app.config import settings
from backend.app.mcp_client import MCPClient
from backend.app.agent.graph import build_graph
from backend.app.agent.state import AgentState
from backend.app.events import SSEData
from backend.app.session_manager import SessionManager

session_manager = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    logger.add(f"{settings.data_dir}/browsepilot.log", rotation="10 MB", level="DEBUG")
    logger.info("BrowsePilot backend starting (model={}, mcp={})", settings.llm_model, settings.mcp_server_url)
    yield
    logger.info("BrowsePilot backend shutting down")


app = FastAPI(title="BrowsePilot API", version="0.1.0", lifespan=lifespan)


def filter_user_input(text: str) -> str:
    """Filter user input: truncate long text, remove control characters."""
    if not isinstance(text, str):
        return ""
    text = text[:2000]
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text.strip()


@app.post("/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    task = body.get("task", "")
    session_id = body.get("session_id", str(uuid.uuid4())[:8])

    task = filter_user_input(task)
    if not task:
        raise HTTPException(status_code=400, detail="task is required")

    session_manager.create_session(session_id)
    session_manager.update(session_id, task=task)
    logger.info("Starting session {} with task: {}", session_id, task[:80])

    mcp_client = MCPClient(settings.mcp_server_url)

    async def event_generator():
        final_state = {}
        try:
            await mcp_client.connect()
            graph = build_graph(mcp_client)

            initial_state: AgentState = {
                "messages": [],
                "task": task,
                "plan": [],
                "execution_log": [],
                "retry_count": 0,
                "need_replan": False,
                "final_answer": "",
                "token_usage": {"prompt": 0, "completion": 0},
            }

            async for event in graph.astream(initial_state, {"recursion_limit": 30}):
                for node_name, node_output in event.items():
                    if node_name == "plan":
                        yield SSEData.thinking_status("planning", "正在分析任务并制定执行计划...")
                        steps = node_output.get("plan", [])
                        tokens = node_output.get("token_usage", {})
                        yield SSEData.plan_generated(steps, tokens)

                    elif node_name == "execute":
                        if node_output.get("execution_log"):
                            last_log = node_output["execution_log"][-1]
                            step_index = len(node_output["execution_log"]) - 1
                            yield SSEData.thinking_status(
                                "executing",
                                f"正在执行: {last_log['step']}",
                                step_index + 1,
                                0,
                            )
                            yield SSEData.step_start(last_log["step"], step_index)
                            result = last_log.get("result", {})
                            if isinstance(result, dict) and result.get("screenshot_base64"):
                                yield SSEData.screenshot(
                                    result["screenshot_base64"],
                                    last_log.get("timestamp", ""),
                                )
                            yield SSEData.step_end(last_log["step"], result)

                    elif node_name == "reflect":
                        yield SSEData.thinking_status("reflecting", "正在反思执行结果...")
                        decision = "replan" if node_output.get("need_replan") else "success"
                        yield SSEData.reflection(decision, "")

                    elif node_name == "replan":
                        yield SSEData.thinking_status("replanning", "正在重新规划替代方案...")
                        yield SSEData.replan(node_output.get("plan", []))

                    elif node_name == "answer":
                        yield SSEData.thinking_status("answering", "正在生成最终回答...")
                        final = node_output.get("final_answer", "")
                        tokens = node_output.get("token_usage", {})
                        total = tokens.get("prompt", 0) + tokens.get("completion", 0)
                        yield SSEData.final_answer(final, total)
                        final_state = node_output

                    # Token updates from any node
                    if node_output.get("token_usage"):
                        tu = node_output["token_usage"]
                        yield SSEData.token_update(
                            tu.get("prompt", 0), tu.get("completion", 0)
                        )

            # Persist session
            if final_state:
                session_manager.update(session_id,
                    execution_log=final_state.get("execution_log", []),
                    final_answer=final_state.get("final_answer", ""),
                    token_usage=final_state.get("token_usage", {}),
                )
            session_manager.persist(session_id)

            # Schedule cleanup (non-blocking)
            asyncio.create_task(
                session_manager.schedule_cleanup(session_id, mcp_client)
            )

        except Exception as e:
            logger.exception("Error in session {}", session_id)
            yield SSEData.error(str(e))
            try:
                await mcp_client.close()
            except Exception:
                pass

    return EventSourceResponse(event_generator())


@app.get("/history/{session_id}")
async def get_history(session_id: str):
    data = session_manager.get_history(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="session not found")
    return JSONResponse(content=data)


@app.get("/replay/{session_id}")
async def get_replay(session_id: str):
    data = session_manager.get_replay(session_id)
    return JSONResponse(content=data)


@app.get("/sessions")
async def list_sessions():
    return JSONResponse(content=session_manager.list_sessions())


@app.get("/health")
async def health():
    return {"status": "ok"}
