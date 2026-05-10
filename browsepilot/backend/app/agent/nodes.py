"""LangGraph nodes: plan, execute, reflect, replan, answer."""

import json
import re
import os
import base64
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from backend.app.agent.state import AgentState
from backend.app.config import settings


def extract_json(text: str) -> str | None:
    """Extract JSON string from LLM response. Handles markdown wrapping and extra text."""
    # 1. Try ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    # 2. Find first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return None


def repair_json(candidate: str) -> str:
    """Fix common JSON errors: trailing commas, single-quote keys/values."""
    # Remove trailing commas before } or ]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    # Single-quoted keys: 'key': → "key":
    candidate = re.sub(r"'([^']*)'\s*:", r'"\1":', candidate)
    # Single-quoted values: : 'value' → : "value"
    candidate = re.sub(r":\s*'([^']*)'", r': "\1"', candidate)
    return candidate


async def parse_llm_json(
    llm,
    messages: list,
    node_name: str,
    fallback: dict,
    max_retries: int = 1,
) -> tuple[dict, dict | None]:
    """Unified LLM JSON invoke + parse + retry + fallback.

    Returns:
        (parsed_dict, token_usage_dict_or_None)
    """
    for attempt in range(max_retries + 1):
        try:
            response = await llm.ainvoke(messages)
            usage = response.usage_metadata
            text = response.content if hasattr(response, "content") else str(response)

            candidate = extract_json(text)
            if candidate is not None:
                try:
                    return json.loads(candidate), usage
                except json.JSONDecodeError:
                    repaired = repair_json(candidate)
                    try:
                        result = json.loads(repaired)
                        logger.info("[{}] JSON repaired successfully", node_name)
                        return result, usage
                    except json.JSONDecodeError as e:
                        logger.warning("[{}] JSON parse failed attempt {}: {}", node_name, attempt + 1, str(e)[:200])

            if attempt < max_retries:
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": "Your response format was incorrect. Return ONLY a JSON object, nothing else.",
                })
                continue

        except Exception as e:
            logger.error("[{}] LLM call failed: {}", node_name, str(e)[:200])
            raise

    logger.warning("[{}] JSON parse failed after {} retries, using fallback", node_name, max_retries)
    return fallback, None


def get_llm():
    """Get the main (big) LLM instance for plan/execute/reflect/replan/answer."""
    return ChatOpenAI(
        model=settings.big_model,
        api_key=settings.big_model_api_key or settings.openai_api_key,
        base_url=settings.big_model_base_url or settings.openai_base_url,
    )


def get_small_llm():
    """Get the small LLM instance for intent classification."""
    return ChatOpenAI(
        model=settings.small_model,
        api_key=settings.small_model_api_key or settings.openai_api_key,
        base_url=settings.small_model_base_url or settings.openai_base_url,
    )


CLASSIFY_PROMPT = """You are an intent classifier. Analyze the user's input and determine which category it belongs to:

1. chitchat — Casual conversation, greetings, small talk unrelated to browser operations
   Examples:
   - "Hello" / "Who are you" / "How's the weather"
   - "Thank you" / "Goodbye"

2. knowledge_qa — Questions that need knowledge/explanation, no browser operations needed
   Examples:
   - "Explain machine learning classification methods"
   - "What is Python's GIL"
   - "Compare React vs Vue"

3. browser_task — Tasks that need to open a browser and perform specific operations
   Examples:
   - "Open Baidu and search for LangChain"
   - "Find Python web scraping projects on GitHub"
   - "Show me what's on the Baidu homepage"

Rules:
- Casual chat, greetings, asking who you are → chitchat
- Knowledge questions that DON'T need a browser → knowledge_qa
- Tasks requiring opening web pages, clicking, typing, screenshots → browser_task

Return JSON: {"intent": "chitchat|knowledge_qa|browser_task"}
Return ONLY JSON, nothing else."""


async def classify_node(state: AgentState) -> dict:
    """Classify user intent using the small model."""
    logger.info("[classify_node] Classifying: {}", state["task"][:80])
    llm = get_small_llm()

    result, usage = await parse_llm_json(
        llm=llm,
        messages=[
            SystemMessage(content=CLASSIFY_PROMPT),
            HumanMessage(content=state["task"]),
        ],
        node_name="classify",
        fallback={"intent": "browser_task"},
    )

    intent = result.get("intent", "browser_task")
    if intent not in ("chitchat", "knowledge_qa", "browser_task"):
        logger.warning("[classify_node] Unknown intent '{}', defaulting to browser_task", intent)
        intent = "browser_task"

    return {
        "intent": intent,
    }


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

重要：get_page_structure 工具可以提取页面上所有输入框、按钮、链接及其 CSS 选择器，在执行任何点击或输入操作前，必须先用它获取选择器。

请根据用户任务，生成一个JSON格式的执行步骤列表。每个步骤是一个自然语言描述的简单操作。
规则：
1. 导航到页面后，始终先获取页面结构（get_page_structure）找到目标元素的精确选择器
2. 根据页面结构中的实际选择器执行操作
3. 不要猜测选择器（如 input[type='text']），应从页面结构中获取

格式示例：["导航到 https://github.com", "获取页面结构，找到搜索框的选择器", "在找到的搜索框中输入关键字", "获取页面结构，找到搜索按钮的选择器", "点击搜索按钮", "获取搜索结果页面内容", "回答用户"]
只返回JSON数组，不要包含其他内容。步骤要具体、可执行。"""

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

    # Build tool descriptions for LLM tool selection
    tools_desc = "\n".join(
        f"- {t.name}: {t.description}"
        for t in langchain_tools
    )

    # Build context from recent execution results (especially get_page_structure output)
    recent_context = ""
    for i, entry in enumerate(state["execution_log"]):
        result = entry.get("result", {})
        if isinstance(result, dict) and result.get("structure"):
            # Found page structure — extract selectors for the LLM
            s = result["structure"]
            recent_context += f"\n页面可用元素（来自之前的get_page_structure）：\n"
            if s.get("inputs"):
                recent_context += "输入框: " + json.dumps(s["inputs"][:10], ensure_ascii=False) + "\n"
            if s.get("buttons"):
                recent_context += "按钮: " + json.dumps(s["buttons"][:10], ensure_ascii=False) + "\n"
            if s.get("links"):
                recent_context += "链接: " + json.dumps(s["links"][:5], ensure_ascii=False) + "\n"
        elif isinstance(result, dict) and result.get("content"):
            recent_context += f"\n页面文本摘要（前500字）：{result['content'][:500]}\n"

    tool_selection_prompt = (
        '你是一个浏览器操作执行器。当前需要执行的步骤是："' + current_step + '"\n\n'
        "可用工具：\n" + tools_desc + "\n\n"
        + recent_context + "\n"
        '关键规则（必须遵守，违反会导致任务失败）：\n'
        '1. 如果上方提供了"页面可用元素"，你必须从其中选择一个匹配的 selector，完全照抄，不得修改\n'
        '2. 例如：如果结构中有 {"selector": "#kw", "tag": "input", "type": "text"}，输入步骤必须用 "#kw"\n'
        '3. 绝对禁止使用自己编造的选择器（如 #chat-textarea、#chat-submit-button、input[type="text"]）\n'
        '4. 如果还没有页面结构信息，先调用 get_page_structure 获取\n'
        '5. get_content 返回页面文本，可用于理解页面内容\n\n'
        '请用JSON格式返回要调用的工具和参数：\n'
        '{"tool": "工具名", "arguments": {"参数名": "参数值"}}\n'
        '如果这个步骤不需要浏览器工具（例如等待、思考、分析类步骤），返回：{"tool": "none", "arguments": {}}\n'
        "只返回JSON对象，不要其他内容。"
    )

    response = await llm.ainvoke([
        SystemMessage(content=tool_selection_prompt),
        HumanMessage(content=current_step),
    ])

    result = {}
    tool_used = "none"

    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        tool_selection = json.loads(content)

        if tool_selection.get("tool") and tool_selection["tool"] != "none":
            tool_used = tool_selection["tool"]
            arguments = tool_selection.get("arguments", {})
            logger.info("[execute_node] Calling tool {} with args {}", tool_used, arguments)
            result = await mcp_client.call_tool(tool_used, arguments)
        else:
            result = {"status": "skipped", "reason": "no_tool_needed"}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("[execute_node] Tool selection failed: {}", e)
        result = {"status": "error", "error": f"tool_selection_failed: {str(e)}"}

    # Save screenshot if available
    screenshot_path = ""
    if isinstance(result, dict) and result.get("screenshot_base64"):
        # Check storage before saving screenshot (deferred to avoid circular import)
        skip_screenshot = False
        try:
            from backend.app.main import session_manager
            if not session_manager.check_storage_before_write():
                logger.warning("Skipping screenshot due to storage limit")
                skip_screenshot = True
        except ImportError:
            pass  # Continue with screenshot save

        if not skip_screenshot:
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
    """Generate the final natural language answer based on extracted page content."""
    logger.info("[answer_node] Generating final answer")
    llm = get_llm()

    # Collect actual page content from execution log (get_content results)
    page_contents = []
    step_summaries = []
    for e in state["execution_log"]:
        step_info = f"- {e['step']}: "
        result = e.get("result", {})
        if isinstance(result, dict) and result.get("status") == "success":
            step_info += "成功"
            if result.get("content"):
                content = result["content"]
                page_contents.append({"step": e["step"], "content": content})
                step_info += f"，提取到 {len(content)} 字内容"
            elif result.get("structure"):
                s = result["structure"]
                inputs_count = len(s.get("inputs", []))
                buttons_count = len(s.get("buttons", []))
                step_info += f"，发现 {inputs_count} 个输入框、{buttons_count} 个按钮"
        elif isinstance(result, dict) and result.get("status") == "error":
            err = result.get("error", "unknown")
            step_info += f"失败 — {err}"
        else:
            step_info += "完成"
        step_summaries.append(step_info)

    # Build context with actual page content
    content_section = ""
    if page_contents:
        content_section = "\n\n实际提取的网页内容：\n"
        for pc in page_contents:
            content_section += f"\n--- 来自步骤 '{pc['step']}' ---\n{pc['content'][:3000]}\n"

    answer_prompt = f"""你是一个智能浏览器助手，请根据以下执行记录和实际提取的网页内容，回答用户问题。

用户任务：{state['task']}

执行过程：
{chr(10).join(step_summaries)}
{content_section}

要求：
1. 基于实际提取的网页内容回答用户，直接给出用户想要的信息
2. 如果内容是搜索结果/天气/新闻等，提取关键信息并整理成易读的格式
3. 如果适合，可以提供相关建议（如出行建议、注意事项等）
4. 用自然语言，简洁但完整，不要只列出步骤
5. 如果关键步骤失败导致无法获取信息，如实说明并给出替代建议
6. 不要提及“步骤X”、执行过程等技术细节，直接给用户自然回答"""

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
