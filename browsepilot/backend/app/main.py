"""FastAPI application entry point with SSE streaming task execution."""

import uuid
import json
import asyncio
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse
from loguru import logger
import sys

from backend.app.config import settings, get_mcp_server_config
from backend.app.mcp_client import MCPClient
from backend.app.agent.graph import build_graph
from backend.app.agent.state import AgentState
from backend.app.events import SSEData
from backend.app.session_manager import SessionManager

session_manager = SessionManager(max_active_sessions=settings.max_active_sessions)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    logger.add(f"{settings.data_dir}/browsepilot.log", rotation="10 MB", level="DEBUG")
    logger.info("BrowsePilot backend starting (model={})", settings.big_model)
    session_manager.cleanup_on_startup()
    yield
    logger.info("BrowsePilot backend shutting down")


app = FastAPI(title="BrowsePilot API", version="0.1.0", lifespan=lifespan)

screenshots_dir = Path(settings.data_dir) / "screenshots"
screenshots_dir.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=str(screenshots_dir)), name="screenshots")


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

    mcp_client = MCPClient(get_mcp_server_config("browser-mcp"))

    async def event_generator():
        async def _cleanup_session():
            """Persist partial state and close MCP on exception."""
            try:
                if 'graph' in dir() and 'graph_config' in dir():
                    state_snapshot = await graph.aget_state(graph_config)
                    if state_snapshot and state_snapshot.values:
                        session_manager.update(session_id,
                            execution_log=state_snapshot.values.get("execution_log", []),
                            final_answer=state_snapshot.values.get("final_answer", ""),
                            token_usage=state_snapshot.values.get("token_usage", {}),
                        )
                        session_manager.persist(session_id)
            except Exception:
                pass
            try:
                await mcp_client.close()
            except Exception:
                pass

        try:
            graph = build_graph(mcp_client, lazy_mcp=True)
            # MCP will be connected lazily when classify routes to browser_task

            initial_state: AgentState = {
                "messages": [],
                "task": task,
                "intent": "",
                "plan": [],
                "execution_log": [],
                "degradation_log": [],
                "retry_count": 0,
                "need_replan": False,
                "final_answer": "",
                "total_steps": 0,
                "token_usage": {"prompt": 0, "completion": 0, "breakdown": {}},
                "consecutive_failures": 0,
                "stagnation_count": 0,
                "replan_count": 0,
                "stagnation_warning": False,
                "completion_check_count": 0,
            }

            graph_config = {
                "recursion_limit": 100,
                "configurable": {"thread_id": session_id},
            }

            yield SSEData.session_created(session_id)

            # Stream with session timeout via asyncio.wait_for on each __anext__()
            timeout = getattr(settings, 'session_timeout_seconds', 300)
            deadline = time.monotonic() + timeout
            astream = graph.astream(initial_state, graph_config)
            final_state = None

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning("Session {} timed out after {}s", session_id, timeout)
                    yield SSEData.error("Session timed out. Partial results are shown below.")
                    break
                try:
                    event = await asyncio.wait_for(astream.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning("Session {} timed out during stream wait", session_id)
                    yield SSEData.error("Session timed out. Partial results are shown below.")
                    break

                for node_name, node_output in event.items():
                    if node_name == "classify":
                        yield SSEData.thinking_status("classifying", "正在分析用户意图...")
                        intent = node_output.get("intent", "unknown")

                    elif node_name == "plan":
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

                    # Token updates from any node
                    if node_output.get("token_usage"):
                        tu = node_output["token_usage"]
                        yield SSEData.token_update(
                            tu.get("prompt", 0), tu.get("completion", 0)
                        )

            # Get final state from LangGraph native state (checkpointer resumes, no rerun)
            try:
                state_snapshot = await graph.aget_state(graph_config)
                if state_snapshot and state_snapshot.values:
                    final_state = state_snapshot.values
            except Exception as e:
                logger.warning("Failed to get final state from graph: {}", e)

            # Persist session using LangGraph native final state
            if final_state:
                session_manager.update(session_id,
                    execution_log=final_state.get("execution_log", []),
                    final_answer=final_state.get("final_answer", ""),
                    token_usage=final_state.get("token_usage", {}),
                )
            session_manager.persist(session_id)

            # Close MCP connection promptly (don't wait for TTL)
            await mcp_client.close()

            # Schedule session cleanup (disk cleanup only)
            asyncio.create_task(
                session_manager.schedule_cleanup(session_id)
            )

        except RuntimeError as e:
            if "cancel scope" in str(e):
                logger.debug("Session {} anyio cancel scope cleanup: {}", session_id, e)
            else:
                logger.exception("Runtime error in session {}", session_id)
                yield SSEData.error(str(e))
            await _cleanup_session()
        except Exception as e:
            logger.exception("Error in session {}", session_id)
            yield SSEData.error(str(e))
            await _cleanup_session()

    async def sse_formatted_generator():
        async for event in event_generator():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        sse_formatted_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/history/{session_id}")
async def get_history(session_id: str):
    data = session_manager.get_history(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="session not found")
    return JSONResponse(content=data)


@app.get("/replay/{session_id}")
async def get_replay(session_id: str):
    session = session_manager.get_history(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    steps = []
    for i, e in enumerate(session.get("execution_log", [])):
        step_data = {
            "step_index": i,
            "step": e.get("step", ""),
            "screenshot_path": e.get("screenshot_path", ""),
            "timestamp": e.get("timestamp", ""),
            "result": (e.get("result", {}) if isinstance(e.get("result"), dict) else {}),
        }
        steps.append(step_data)
    return JSONResponse(content=steps)


@app.get("/sessions")
async def list_sessions():
    return JSONResponse(content=session_manager.list_sessions())


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    ok = session_manager.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return JSONResponse(content={"ok": True})


@app.get("/health")
async def health():
    return {"status": "ok"}
