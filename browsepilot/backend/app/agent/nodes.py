"""LangGraph nodes: plan, execute, reflect, replan, answer."""

import json
import os
import base64
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from backend.app.agent.state import AgentState
from backend.app.config import settings


def get_llm():
    """Get configured LLM instance."""
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


async def plan_node(state: AgentState, mcp_client) -> dict:
    """Generate a structured execution plan from the user task."""
    logger.info("[plan_node] Generating plan for task: {}", state["task"][:80])
    llm = get_llm()

    tools_schema = await mcp_client.get_tools_schema()
    tools_desc = "\n".join(
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in tools_schema
    )

    system_prompt = f"""你是一个浏览器自动化规划专家。你可以使用以下工具：
{tools_desc}

请根据用户任务，生成一个JSON格式的执行步骤列表。每个步骤是一个自然语言描述的简单操作。
格式示例：["导航到 https://github.com", "搜索仓库 langchain-ai/langgraph", "提取 Star 数量", "回答用户"]
只返回JSON数组，不要包含其他内容。步骤要具体、可执行，避免模糊描述。"""

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["task"]),
    ])

    try:
        plan_text = response.content.strip()
        if "```" in plan_text:
            plan_text = plan_text.split("```")[1]
            if plan_text.startswith("json"):
                plan_text = plan_text[4:]
        plan = json.loads(plan_text)
    except json.JSONDecodeError:
        logger.warning("[plan_node] Failed to parse plan JSON, using fallback")
        plan = [state["task"], "回答用户"]

    token_usage = {
        "prompt": response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0,
        "completion": response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0,
    }

    return {
        "plan": plan,
        "retry_count": 0,
        "need_replan": False,
        "execution_log": [],
        "token_usage": token_usage,
    }


async def execute_node(state: AgentState, mcp_client, langchain_tools: list) -> dict:
    """Execute the first step in the plan using the appropriate MCP tool."""
    if not state["plan"]:
        logger.info("[execute_node] No steps remaining in plan")
        return {}

    current_step = state["plan"][0]
    logger.info("[execute_node] Executing step: {}", current_step)

    llm = get_llm()
    llm_with_tools = llm.bind_tools(langchain_tools)

    tool_selection_prompt = f"""你是一个浏览器操作执行器。当前需要执行的步骤是："{current_step}"

请选择一个工具并调用它。如果这个步骤不需要浏览器工具操作（例如已经是分析或答复类的步骤），请不要调用工具。"""

    response = await llm_with_tools.ainvoke([
        SystemMessage(content=tool_selection_prompt),
        HumanMessage(content=current_step),
    ])

    tool_calls = response.tool_calls if hasattr(response, "tool_calls") and response.tool_calls else []

    result = {}
    tool_used = "none"
    if tool_calls:
        tc = tool_calls[0]
        tool_used = tc["name"]
        arguments = tc["args"]
        result = await mcp_client.call_tool(tool_used, arguments)

    # Save screenshot if available
    screenshot_path = ""
    if isinstance(result, dict) and result.get("screenshot_base64"):
        step_index = len(state["execution_log"])
        os.makedirs(f"{settings.data_dir}/screenshots", exist_ok=True)
        screenshot_path = f"{settings.data_dir}/screenshots/step_{step_index}_{datetime.now(timezone.utc).strftime('%H%M%S')}.png"
        try:
            with open(screenshot_path, "wb") as f:
                f.write(base64.b64decode(result["screenshot_base64"]))
        except Exception as e:
            logger.warning("[execute_node] Failed to save screenshot: {}", e)
            screenshot_path = ""

    new_log = state["execution_log"] + [{
        "step": current_step,
        "tool": tool_used,
        "result": result,
        "screenshot_path": screenshot_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "retry_count": state["retry_count"],
    }]

    new_plan = state["plan"][1:]

    return {
        "execution_log": new_log,
        "plan": new_plan,
        "messages": state["messages"] + [
            HumanMessage(content=f"步骤: {current_step}"),
            HumanMessage(content=f"结果: {json.dumps(result, ensure_ascii=False)[:500]}"),
        ],
    }


async def reflect_node(state: AgentState) -> dict:
    """Analyze the last execution result and decide next action."""
    if not state["execution_log"]:
        return {"need_replan": False}

    last = state["execution_log"][-1]
    is_error = isinstance(last["result"], dict) and last["result"].get("status") == "error"
    error_msg = last["result"].get("error", "") if isinstance(last["result"], dict) else ""

    if not is_error:
        logger.info("[reflect_node] Step succeeded: {}", last["step"])
        return {"need_replan": False, "retry_count": 0}

    logger.info("[reflect_node] Step failed: {} — error: {}", last["step"], error_msg)

    if state["retry_count"] < 2:
        logger.info("[reflect_node] Retrying (attempt {})", state["retry_count"] + 1)
        return {"need_replan": False, "retry_count": state["retry_count"] + 1}

    # Max retries reached — use LLM to analyze and prepare for replan
    logger.info("[reflect_node] Max retries reached, triggering replan")
    llm = get_llm()

    # Try screenshot if vision enabled, but gracefully degrade
    analysis_context = f"""失败步骤：{last['step']}
错误信息：{error_msg}
工具：{last['tool']}
已完成步骤：{json.dumps([e['step'] for e in state['execution_log']], ensure_ascii=False)}"""

    if settings.llm_vision_enabled and last.get("screenshot_path"):
        try:
            with open(last["screenshot_path"], "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            logger.info("[reflect_node] Using screenshot for visual analysis")
        except Exception as e:
            logger.warning("[reflect_node] Cannot read screenshot, falling back to text-only: {}", e)
            img_b64 = None
    else:
        img_b64 = None

    analysis_prompt = f"""你是一个浏览器自动化调试专家。一个操作步骤失败了，请分析原因。

{analysis_context}

请用简短的一句话分析失败原因，并给出替代方案建议。"""

    try:
        response = await llm.ainvoke([HumanMessage(content=analysis_prompt)])
        analysis = response.content.strip()
    except Exception as e:
        logger.warning("[reflect_node] LLM analysis failed: {}, using fallback", e)
        analysis = f"操作 '{last['step']}' 失败，尝试替代方案"

    return {
        "need_replan": True,
        "retry_count": 0,
        "messages": state["messages"] + [HumanMessage(content=f"反思结果: {analysis}")],
    }


async def replan_node(state: AgentState, mcp_client) -> dict:
    """Generate a new plan based on what has been done and what failed."""
    logger.info("[replan_node] Regenerating plan based on current state")
    llm = get_llm()

    completed = [e["step"] for e in state["execution_log"] if e.get("result", {}).get("status") != "error"]
    failed = [e for e in state["execution_log"] if e.get("result", {}).get("status") == "error"]
    failed_desc = "\n".join(f"  - {e['step']}: {e.get('result', {}).get('error', 'unknown')}" for e in failed)

    tools_schema = await mcp_client.get_tools_schema()
    tools_desc = "\n".join(
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in tools_schema
    )

    replan_prompt = f"""你是一个浏览器自动化规划专家。原计划部分失败，需要重新规划剩余步骤。

原始任务：{state['task']}
已完成步骤：{json.dumps(completed, ensure_ascii=False)}
失败步骤：
{failed_desc}

可用工具：
{tools_desc}

请生成一个新的JSON执行步骤列表，绕过已失败的步骤，尝试替代方案。
格式：["步骤1", "步骤2", ...]
只返回JSON数组。"""

    try:
        response = await llm.ainvoke([HumanMessage(content=replan_prompt)])
        plan_text = response.content.strip()
        if "```" in plan_text:
            plan_text = plan_text.split("```")[1]
            if plan_text.startswith("json"):
                plan_text = plan_text[4:]
        new_plan = json.loads(plan_text)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("[replan_node] Failed to parse replan JSON: {}", e)
        new_plan = ["回答用户（基于已完成步骤给出部分结果）"]

    return {"plan": new_plan, "need_replan": False, "retry_count": 0}


async def answer_node(state: AgentState) -> dict:
    """Generate the final natural language answer."""
    logger.info("[answer_node] Generating final answer")
    llm = get_llm()

    summary = "\n".join(
        f"- {e['step']}: {'成功' if e.get('result', {}).get('status') == 'success' else '失败 — ' + str(e.get('result', {}).get('error', 'unknown'))}"
        for e in state["execution_log"]
    )

    answer_prompt = f"""你是一个智能浏览器助手。请根据以下执行记录回答用户问题。

用户任务：{state['task']}

执行记录：
{summary}

请用自然语言简洁地回答用户，基于实际执行结果。如果部分步骤失败，如实说明。"""

    response = await llm.ainvoke([HumanMessage(content=answer_prompt)])
    final_answer = response.content.strip()

    total_tokens = dict(state.get("token_usage", {"prompt": 0, "completion": 0}))
    if response.usage_metadata:
        total_tokens["prompt"] = total_tokens.get("prompt", 0) + response.usage_metadata.get("input_tokens", 0)
        total_tokens["completion"] = total_tokens.get("completion", 0) + response.usage_metadata.get("output_tokens", 0)

    return {
        "final_answer": final_answer,
        "token_usage": total_tokens,
        "messages": state["messages"] + [HumanMessage(content=final_answer)],
    }
