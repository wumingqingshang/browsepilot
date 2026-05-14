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
    # 2. Find first { to last } (JSON object — try before array since objects often contain arrays)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start and start < text.find("["):
        return text[start:end + 1]
    # 3. Find first [ to last ] (JSON array)
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    # 4. Fallback: { to } even if [ appears first
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return None


def repair_json(candidate: str) -> str:
    """Fix common JSON errors: trailing commas, single-quote keys/values."""
    # Remove trailing commas before } or ]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    # Single-quoted keys: 'key': -> "key":
    candidate = re.sub(r"'([^']*)'\s*:", r'"\1":', candidate)
    # Single-quoted values: : 'value' -> : "value"
    candidate = re.sub(r":\s*'([^']*)'", r': "\1"', candidate)
    return candidate


# --- Tool scoring classifier ---

TOOL_RULES = {
    "navigate": {
        "keywords": ["导航到", "访问", "打开", "跳转到"],
        "patterns": [r"https?://\S+", r"[a-z]+\.(com|cn|org)"],
    },
    "get_page_structure": {
        "keywords": ["页面结构", "获取结构", "选择器", "CSS", "元素列表"],
        "patterns": [r"获取.*结构", r"找到.*选择器"],
    },
    "type_text": {
        "keywords": ["输入", "键入", "填写", "搜索"],
        "patterns": [r"在.{0,20}(输入|键入|填写|搜索)"],
    },
    "click": {
        "keywords": ["点击", "按下", "提交"],
        "patterns": [r"点击.{0,20}(按钮|链接|搜索)"],
    },
    "get_content": {
        "keywords": ["页面内容", "获取内容", "提取"],
        "patterns": [r"获取.*(内容|文字|数据)"],
    },
    "screenshot": {
        "keywords": ["截图"],
        "patterns": [r"截图|screenshot"],
    },
    "scroll": {
        "keywords": ["滚动", "翻页"],
        "patterns": [r"滚动|scroll|翻页"],
    },
    "execute_script": {
        "keywords": ["脚本", "执行脚本"],
        "patterns": [r"执行.*脚本|execute_script"],
    },
}

THRESHOLD = 2  # minimum score to trust classifier over LLM


def classify_tool(step: str) -> str | None:
    """Score all tools against the step description. Returns tool name
    if best score >= THRESHOLD, else None (LLM fallback)."""
    best_tool = None
    best_score = 0
    for tool_name, rules in TOOL_RULES.items():
        score = 0
        for kw in rules["keywords"]:
            if kw in step:
                score += 1
        for pat in rules["patterns"]:
            if re.search(pat, step):
                score += 2
        if score > best_score:
            best_score = score
            best_tool = tool_name
    return best_tool if best_score >= THRESHOLD else None


def compute_plan_similarity(old_plan: list[str], new_plan: list[str]) -> float:
    """Jaccard similarity on character-level tokens. No LLM."""
    def tokenize(steps):
        tokens = set()
        for s in steps:
            for ch in s.replace(" ", ""):
                tokens.add(ch)
        return tokens
    old_tokens = tokenize(old_plan)
    new_tokens = tokenize(new_plan)
    if not old_tokens or not new_tokens:
        return 0.0
    return len(old_tokens & new_tokens) / len(old_tokens | new_tokens)


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


def accumulate_tokens(current: dict, usage, node_name: str = "") -> dict:
    """Accumulate token usage with per-node breakdown."""
    if usage is None:
        return dict(current)
    # Handle both usage_metadata dict and AIMessage with usage_metadata attribute
    if hasattr(usage, 'usage_metadata'):
        usage = usage.usage_metadata
    if not usage:
        return dict(current)
    add_prompt = usage.get("input_tokens", 0)
    add_completion = usage.get("output_tokens", 0)
    return {
        "prompt": current.get("prompt", 0) + add_prompt,
        "completion": current.get("completion", 0) + add_completion,
        "breakdown": {
            **current.get("breakdown", {}),
            node_name: {"prompt": add_prompt, "completion": add_completion},
        },
    }


def estimate_tokens(text: str) -> int:
    """Conservative token estimate: 2 chars per token."""
    return len(text) // 2


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
- Casual chat, greetings, asking who you are -> chitchat
- Knowledge questions that DON'T need a browser -> knowledge_qa
- Tasks requiring opening web pages, clicking, typing, screenshots -> browser_task

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

    token_usage = accumulate_tokens(state.get("token_usage", {}), usage, "classify")

    return {
        "intent": intent,
        "token_usage": token_usage,
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

搜索引擎选择：
- 默认使用 Bing (https://www.bing.com) 进行搜索
- 避免使用百度——百度有严格的反爬验证，访问经常失败
- 仅当用户明确要求使用特定搜索引擎时才使用其他引擎

请根据用户任务，生成一个JSON格式的执行步骤列表。每个步骤是一个自然语言描述的简单操作。
规则：
1. 导航到页面后，始终先获取页面结构（get_page_structure）找到目标元素的精确选择器
2. 根据页面结构中的实际选择器执行操作
3. 不要猜测选择器（如 input[type='text']），应从页面结构中获取
4. 搜索类任务默认访问 https://www.bing.com，不要使用百度

格式示例：["导航到 https://github.com", "获取页面结构，找到搜索框的选择器", "在找到的搜索框中输入关键字", "获取页面结构，找到搜索按钮的选择器", "点击搜索按钮", "获取搜索结果页面内容", "回答用户"]
只返回JSON数组，不要包含其他内容。步骤要具体、可执行。"""

    plan, usage = await parse_llm_json(
        llm=llm,
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=state["task"]),
        ],
        node_name="plan",
        fallback=[state["task"], "回答用户"],
    )
    if not isinstance(plan, list):
        logger.warning("[plan_node] Plan is not a list, using fallback")
        plan = [state["task"], "回答用户"]

    token_usage = accumulate_tokens({}, usage, "plan")

    # Self-check: can this plan answer the user's question?
    self_check_prompt = f"""User task: {state["task"]}
Generated plan: {json.dumps(plan, ensure_ascii=False)}

After executing this plan, will the collected information be sufficient to answer the user's original question?
If not, append the missing steps to the end of the plan.
Return JSON: {{"sufficient": true/false, "extra_steps": []}}
Return ONLY JSON."""

    try:
        check_llm = get_llm()
        check_result, check_usage = await parse_llm_json(
            llm=check_llm,
            messages=[
                SystemMessage(content=self_check_prompt),
                HumanMessage(content="请检查计划是否充分"),
            ],
            node_name="plan_self_check",
            fallback={"sufficient": True, "extra_steps": []},
        )
        if not check_result.get("sufficient", True):
            extra = check_result.get("extra_steps", [])
            if extra:
                plan.extend(extra)
                logger.info("[plan_node] Self-check added {} extra steps", len(extra))
        if check_usage:
            token_usage = accumulate_tokens(token_usage, check_usage, "plan_self_check")
    except Exception as e:
        logger.warning("[plan_node] Self-check failed, using plan as-is: {}", e)

    return {
        "plan": plan,
        "retry_count": 0,
        "need_replan": False,
        "execution_log": state.get("execution_log") or [],
        "token_usage": token_usage,
    }


EXECUTE_SYSTEM_PROMPT = """You are a browser automation execution expert.
Available tools:
{tools_desc}

Core rules:
1. If the previous step already used get_page_structure and returned selectors,
   reuse those selectors. Only call get_page_structure again when:
   - The page has navigated to a new URL, OR
   - The previous structure did not contain the element you need
2. ONLY use selectors returned by get_page_structure — never invent or guess selectors
3. Execute ONE operation at a time

Recent execution context:
{recent_context}

Select the next tool to execute based on the user's task and current context.
Return JSON: {{"tool": "tool_name", "arguments": {{...}}, "step": "brief step description"}}
Return ONLY JSON."""


async def execute_node(state: AgentState, mcp_client, tools: list) -> dict:
    """Execute the first step in the plan using the appropriate MCP tool."""
    if not state["plan"]:
        logger.info("[execute_node] No steps remaining in plan")
        return {}

    current_step = state["plan"][0]
    logger.info("[execute_node] Executing step: {}", current_step)

    llm = get_llm()

    # Build tool descriptions for LLM tool selection (tools are raw MCP dicts)
    tools_desc = "\n".join(
        f"- {t['name']}: {t.get('description', '')}"
        for t in tools
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

    # Append tool call history so LLM knows what's been done
    if state["execution_log"]:
        recent_context += "\nPreviously executed tools:\n"
        for i, entry in enumerate(state["execution_log"][-5:]):
            tool = entry.get("tool", "unknown")
            status = "success" if entry.get("result", {}).get("status") != "error" else "failed"
            step_desc = entry.get("step", "")[:60]
            recent_context += f"{i+1}. {tool} ({status}) — {step_desc}\n"

    prompt = EXECUTE_SYSTEM_PROMPT.format(
        tools_desc=tools_desc,
        recent_context=recent_context,
    )

    # Scoring classifier hint: if confident, suggest the tool to LLM
    classified_tool = classify_tool(current_step)
    if classified_tool:
        logger.info("[execute_node] Classifier recommends: {} (score >= {})", classified_tool, THRESHOLD)
        prompt += f"\n\nHint: the recommended tool for this step is '{classified_tool}'. "
        prompt += "Use it unless you have a strong reason to pick another tool."

    tool_selection, usage = await parse_llm_json(
        llm=llm,
        messages=[
            SystemMessage(content=prompt),
            HumanMessage(content=current_step),
        ],
        node_name="execute",
        fallback={"tool": "get_content", "arguments": {}, "step": current_step},
    )

    token_usage = accumulate_tokens(state.get("token_usage", {}), usage, "execute")

    result = {}
    tool_used = tool_selection.get("tool", "none") if isinstance(tool_selection, dict) else "none"

    if tool_used and tool_used != "none":
        arguments = tool_selection.get("arguments", {}) if isinstance(tool_selection, dict) else {}
        logger.info("[execute_node] Calling tool {} with args {}", tool_used, arguments)
        try:
            result = await mcp_client.call_tool(tool_used, arguments)
        except Exception as e:
            logger.warning("[execute_node] Tool call failed: {}", e)
            result = {"status": "error", "error": f"tool_call_failed: {str(e)}"}
    else:
        result = {"status": "skipped", "reason": "no_tool_needed"}

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
            step_index = state.get("total_steps", 0)
            session_id = state.get("session_id", "unknown")
            screenshots_dir = f"{settings.data_dir}/screenshots/{session_id}"
            os.makedirs(screenshots_dir, exist_ok=True)
            screenshot_path = f"{screenshots_dir}/step_{step_index}.png"
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

    success = isinstance(result, dict) and result.get("status") != "error"

    if success:
        new_plan = state["plan"][1:]   # Success: advance to next step
        retry_count = 0
    else:
        new_plan = state["plan"]       # Failure: keep current step for retry
        retry_count = state.get("retry_count", 0) + 1

    return {
        "execution_log": new_log,
        "plan": new_plan,
        "retry_count": retry_count,
        "total_steps": state.get("total_steps", 0) + 1,
        "token_usage": token_usage,
        "messages": state["messages"] + [
            HumanMessage(content=f"步骤: {current_step}"),
            HumanMessage(content=f"结果: {json.dumps(result, ensure_ascii=False)[:500]}"),
        ],
    }


# --- Reflect node: two-level reflection ---

def _run_heuristic_checks(state: AgentState) -> dict:
    """Code-level heuristic checks on the last execution step. Zero LLM cost.

    Returns dict with keys: has_issue, issue_type, detail
    """
    if not state.get("execution_log"):
        return {"has_issue": False, "issue_type": None, "detail": ""}

    last_entry = state["execution_log"][-1]
    last_result = last_entry.get("result", {})
    if not isinstance(last_result, dict):
        return {"has_issue": False, "issue_type": None, "detail": ""}

    # Check 1: Page content too short — only for get_content tool
    if last_entry.get("tool") == "get_content":
        content_text = last_result.get("result", last_result.get("content", ""))
        if isinstance(content_text, str) and content_text.strip():
            # Strip HTML tags for meaningful text length check
            import re as _re
            clean = _re.sub(r"<[^>]+>", "", content_text).strip()
            if len(clean) < 50:
                return {
                    "has_issue": True,
                    "issue_type": "content_short",
                    "detail": f"Page content only {len(clean)} meaningful characters",
                }

    # Check 2: URL domain check — compare navigate result with expected domain
    step = last_entry.get("step", "")
    last_url = last_result.get("url", "")
    if last_url and step:
        # Extract expected domain from step description
        import re as _re
        url_match = _re.search(r"https?://([^/\s]+)", step)
        if url_match:
            expected_domain = url_match.group(1)
            actual_domain = _re.sub(r"^https?://", "", last_url).split("/")[0]
            if expected_domain not in actual_domain and actual_domain not in expected_domain:
                return {
                    "has_issue": True,
                    "issue_type": "domain_mutation",
                    "detail": f"Expected {expected_domain}, got {actual_domain}",
                }

    # Check 3: Consecutive similar results (dead loop detection)
    recent = state["execution_log"][-3:]
    if len(recent) >= 3:
        texts = []
        for entry in recent:
            r = entry.get("result", {})
            if isinstance(r, dict):
                t = r.get("result", r.get("content", ""))
                texts.append(str(t)[:200] if isinstance(t, str) else "")
        if all(texts) and len(set(texts)) <= 1:
            return {
                "has_issue": True,
                "issue_type": "similar_results",
                "detail": "Last 3 steps produced identical results",
            }

    # Check 4: No interactive elements (page likely broken or blank)
    structure = last_result.get("structure", {})
    if isinstance(structure, dict):
        input_count = len(structure.get("inputs", []))
        button_count = len(structure.get("buttons", []))
        if input_count == 0 and button_count == 0 and "get_page_structure" in last_entry.get("tool", ""):
            return {
                "has_issue": True,
                "issue_type": "few_elements",
                "detail": "No interactive elements found — page may be blank or broken",
            }

    return {"has_issue": False, "issue_type": None, "detail": ""}


COMPLETION_CHECK_PROMPT = """User's original task: {task}

Summary of executed steps and collected information:
{execution_summary}

Key page contents collected:
{page_contents_summary}

Is the collected information sufficient to adequately answer the user's question?
- If SUFFICIENT: return {{"action": "answer"}}
- If NOT SUFFICIENT: return {{"action": "continue", "extra_steps": ["specific step 1", "specific step 2", ...]}}
  Maximum 3 extra steps. Each step should be a clear, executable browser action.
Return ONLY JSON."""


REFLECT_SYSTEM_PROMPT = """You are a browser automation reflection expert. Analyze the execution result and decide the next action.

If stagnation warning is present: the previous replan produced a highly similar plan. You MUST try a fundamentally different approach — change operation order, try a different navigation path, or fall back to a search engine. If no viable alternative exists, choose answer.

Return JSON: {{"action": "retry|replan|answer", "reason": "brief explanation"}}
Return ONLY JSON."""


def _last_step_failed(state: AgentState) -> bool:
    """Check if the last execution step resulted in an error."""
    if not state.get("execution_log"):
        return False
    last = state["execution_log"][-1]
    result = last.get("result", {})
    return isinstance(result, dict) and result.get("status") == "error"


async def _completion_check(state: AgentState) -> dict:
    """Check if collected info is sufficient to answer user's question."""
    logger.info("[reflect_node] Running completion check...")

    # Build execution summary
    execution_summary = "\n".join(
        f"- {e.get('step', '')}: {str(e.get('result', {}).get('status', 'unknown'))}"
        for e in state.get("execution_log", [])[-10:]
    )

    # Extract page contents
    page_contents = []
    for e in state.get("execution_log", []):
        result = e.get("result", {})
        if isinstance(result, dict):
            content = result.get("result", result.get("content", ""))
            if isinstance(content, str) and len(content) > 20:
                page_contents.append(content[:500])

    context = COMPLETION_CHECK_PROMPT.format(
        task=state["task"],
        execution_summary=execution_summary,
        page_contents_summary="\n---\n".join(page_contents[-5:]) or "(none)",
    )

    llm = get_llm()
    check_result, usage = await parse_llm_json(
        llm=llm,
        messages=[
            SystemMessage(content=context),
            HumanMessage(content="请判断信息是否足够回答用户问题"),
        ],
        node_name="reflect_completion",
        fallback={"action": "answer"},
    )

    action = check_result.get("action", "answer")
    extra_steps = check_result.get("extra_steps", [])

    result = {
        "completion_check_count": state.get("completion_check_count", 0) + 1,
    }

    if usage:
        result["token_usage"] = accumulate_tokens(state.get("token_usage", {}), usage, "reflect")

    if action == "continue" and extra_steps:
        logger.info("[reflect_node] Info insufficient, adding {} extra steps", len(extra_steps))
        result["plan"] = extra_steps
        result["need_replan"] = False
    else:
        logger.info("[reflect_node] Info sufficient, routing to answer")
        result["need_replan"] = False

    return result


async def _llm_reflection(state: AgentState, heuristic_result: dict | None = None) -> dict:
    """LLM-based deep reflection on step failure or heuristic issues."""
    logger.info("[reflect_node] Running LLM deep reflection...")

    # Build context
    context = f"User task: {state['task']}\n\n"

    if state.get("execution_log"):
        last = state["execution_log"][-1]
        context += f"Last step: {last.get('step', '')}\n"
        context += f"Result: {json.dumps(last.get('result', {}), ensure_ascii=False)[:500]}\n"

    if heuristic_result and heuristic_result.get("has_issue"):
        context += f"\nHeuristic check found issue: {heuristic_result.get('issue_type')} — {heuristic_result.get('detail')}\n"

    if state.get("stagnation_warning"):
        context += """\n\n⚠ IMPORTANT WARNING: The previous replan produced a plan highly similar to the old one (>80% similarity).
Current strategy may be in a dead loop. You MUST try a fundamentally different approach:
- Change the order of operations
- Try a different navigation path
- Fall back to a search engine if the current page cannot complete the task
If no viable alternative exists, select answer."""

    context += f"\n\nCurrent remaining plan: {json.dumps(state.get('plan', []), ensure_ascii=False)}\n"

    messages = [
        SystemMessage(content=REFLECT_SYSTEM_PROMPT),
        HumanMessage(content=context),
    ]

    llm = get_llm()
    reflection, usage = await parse_llm_json(
        llm=llm,
        messages=messages,
        node_name="reflect_llm",
        fallback={"action": "answer", "reason": "reflection failed, defaulting to answer"},
    )

    action = reflection.get("action", "answer")
    logger.info("[reflect_node] LLM reflection decision: {} — {}", action, reflection.get("reason", ""))

    result = {}
    if usage:
        result["token_usage"] = accumulate_tokens(state.get("token_usage", {}), usage, "reflect")

    if action == "retry":
        if state.get("retry_count", 0) >= 2:
            # Too many retries — force replan
            result["need_replan"] = True
        else:
            result["need_replan"] = False
    elif action == "replan":
        result["need_replan"] = True
    else:
        result["need_replan"] = False  # answer

    return result


async def reflect_node(state: AgentState) -> dict:
    """Analyze the last execution result and decide next action (two-level reflection)."""
    logger.info("[reflect_node] Reflecting on execution...")

    # Circuit breaker checks — force answer with reason
    if state.get("consecutive_failures", 0) >= 3:
        logger.warning("[reflect_node] Circuit breaker: {} consecutive failures", state["consecutive_failures"])
        return {"plan": [], "need_replan": False,
                "stop_reason": f"连续 {state['consecutive_failures']} 步执行失败，为避免无限重试，按照现有搜集到的材料组织回答"}
    if state.get("replan_count", 0) >= 2:
        logger.warning("[reflect_node] Too many replans: {}", state["replan_count"])
        return {"plan": [], "need_replan": False,
                "stop_reason": f"已进行 {state['replan_count']} 次重新规划，当前任务可能无法通过浏览器自动化完成，按照现有搜集到的材料组织回答"}
    if state.get("stagnation_count", 0) >= 3:
        logger.warning("[reflect_node] Stagnation detected: {}", state["stagnation_count"])
        return {"plan": [], "need_replan": False,
                "stop_reason": "连续多步结果高度相似，判断陷入死循环，按照现有搜集到的材料组织回答"}
    if len(state.get("execution_log", [])) >= 10:
        logger.warning("[reflect_node] Step limit reached: {}", len(state["execution_log"]))
        return {"plan": [], "need_replan": False,
                "stop_reason": "执行步骤已达上限，按照现有搜集到的材料组织回答"}

    # Level 1: Heuristic check on last step (code-level, zero LLM cost)
    heuristic_result = _run_heuristic_checks(state)
    if heuristic_result.get("has_issue"):
        logger.info("[reflect_node] Heuristic check found issue: {} — {}",
                    heuristic_result.get("issue_type"), heuristic_result.get("detail"))

    # Level 1 continued: check if step failed
    last_step_failed_result = _last_step_failed(state)

    # Level 2: Deep reflection triggers
    has_plan = state.get("plan") and len(state["plan"]) > 0

    if not has_plan:
        # Plan is empty — completion check
        completion_check_count = state.get("completion_check_count", 0)
        if completion_check_count >= 1:
            # Already checked once, don't loop
            logger.info("[reflect_node] Completion check already done, routing to answer")
            return {"need_replan": False}

        return await _completion_check(state)

    if not last_step_failed_result and (not heuristic_result or not heuristic_result.get("has_issue")):
        # Step succeeded and no heuristic issues — continue
        logger.info("[reflect_node] Step OK, continuing execution")
        return {"need_replan": False}

    # Level 2: LLM deep reflection
    return await _llm_reflection(state, heuristic_result)


# --- Replan node with vision context ---


def _build_replan_context(state: AgentState):
    """Build replan context, optionally with vision-enabled screenshots.

    Content fields (page HTML/text) are truncated to avoid token explosion.
    """
    text = f"Original task: {state['task']}\n\n"
    text += "Execution log:\n"

    # Build truncated execution log — strip large content fields
    truncated_log = []
    for entry in state.get("execution_log", [])[-5:]:
        e = dict(entry)
        result = e.get("result", {})
        if isinstance(result, dict):
            r = dict(result)
            # Truncate page content and screenshot data to avoid token explosion
            for key in ("result", "content", "screenshot_base64"):
                if key in r and isinstance(r[key], str):
                    r[key] = r[key][:500] + "..." if len(r[key]) > 500 else r[key]
            e["result"] = r
        truncated_log.append(e)
    text += f"{json.dumps(truncated_log, ensure_ascii=False, indent=2)}\n"
    text += f"\nCurrent plan (failed): {json.dumps(state.get('plan', []), ensure_ascii=False)}\n"
    text += f"\nRetry count: {state.get('retry_count', 0)}\n"

    if not settings.llm_vision_enabled:
        return text  # Plain text only

    # Build multimodal content with screenshots
    content: list = [{"type": "text", "text": text}]

    for entry in state.get("execution_log", [])[-3:]:
        result = entry.get("result", {})
        if isinstance(result, dict) and result.get("status") == "error":
            screenshot_path = entry.get("screenshot_path", "")
            if screenshot_path and os.path.exists(screenshot_path):
                try:
                    with open(screenshot_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    })
                    logger.info("[replan_node] Added screenshot for vision analysis")
                except Exception as e:
                    logger.warning("[replan_node] Failed to encode screenshot: {}", e)

    return content


async def replan_node(state: AgentState, mcp_client) -> dict:
    """Generate a new plan based on what has been done and what failed."""
    logger.info("[replan_node] Regenerating plan...")
    llm = get_llm()

    tools_schema = await mcp_client.get_tools_schema()
    tools_desc = "\n".join(
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in tools_schema
    )

    # Build context (with or without vision)
    context_content = _build_replan_context(state)

    REPLAN_PROMPT = f"""You are a browser automation planning expert. Available tools:
{tools_desc}

The previous execution plan failed. Analyze the failure context (and any screenshots provided) to create a new, better plan.

Important:
- Generate a DIFFERENT plan from the failed one. Try alternative approaches.
- Use Bing (https://www.bing.com) for searches. Avoid Baidu — it has strict anti-bot verification.

Generate a JSON array of execution steps. Format: ["step 1", "step 2", ...]
Return ONLY the JSON array, nothing else."""

    # Build messages — HumanMessage accepts both string and list content
    if isinstance(context_content, list):
        messages = [
            SystemMessage(content=REPLAN_PROMPT),
            HumanMessage(content=context_content),
        ]
    else:
        messages = [
            SystemMessage(content=REPLAN_PROMPT),
            HumanMessage(content=context_content),
        ]

    new_plan, usage = await parse_llm_json(
        llm=llm,
        messages=messages,
        node_name="replan",
        fallback=["回答用户（基于已完成步骤给出部分结果）"],
    )
    if not isinstance(new_plan, list):
        logger.warning("[replan_node] Replan result is not a list, using fallback")
        new_plan = ["回答用户（基于已完成步骤给出部分结果）"]

    token_usage = accumulate_tokens(state.get("token_usage", {}), usage, "replan")

    similarity = compute_plan_similarity(state.get("plan", []), new_plan)

    if similarity == 1.0:
        logger.warning("[replan_node] Identical plan generated, giving up")
        return {
            "plan": state.get("plan", []),
            "need_replan": False,
            "stagnation_count": state.get("stagnation_count", 0) + 1,
            "replan_count": state.get("replan_count", 0) + 1,
            "token_usage": token_usage,
        }

    if similarity > 0.8:
        logger.warning("[replan_node] Highly similar plan (sim={:.2f})", similarity)
        return {
            "plan": new_plan,
            "stagnation_count": state.get("stagnation_count", 0) + 1,
            "stagnation_warning": True,
            "replan_count": state.get("replan_count", 0) + 1,
            "need_replan": False,
            "token_usage": token_usage,
        }

    return {
        "plan": new_plan,
        "stagnation_count": 0,
        "stagnation_warning": False,
        "replan_count": state.get("replan_count", 0) + 1,
        "need_replan": False,
        "token_usage": token_usage,
    }


# --- Answer node with dual-path fallback ---


def compress_execution_log(execution_log: list, max_tokens: int = 4000) -> str:
    """Compress execution log: last 3 steps full detail, older steps summary only."""
    if len(execution_log) <= 3:
        parts = []
        for e in execution_log:
            result_str = json.dumps(e.get("result", {}), ensure_ascii=False)[:200]
            parts.append(f"- {e.get('step', '')}: {result_str}")
        return "\n".join(parts)

    recent = execution_log[-3:]
    older = execution_log[:-3]
    parts = ["## Earlier steps (summary)"]
    for e in older:
        status = e.get("result", {}).get("status", "unknown") if isinstance(e.get("result"), dict) else "unknown"
        parts.append(f"- {e.get('step', '')} [{status}]")
    parts.append("\n## Recent steps (detailed)")
    for e in recent:
        result_str = json.dumps(e.get("result", {}), ensure_ascii=False)[:300]
        parts.append(f"- {e.get('step', '')}: {result_str}")
    return "\n".join(parts)


def build_context_with_budget(
    system_prompt: str,
    task: str,
    messages: list,
    execution_log: list,
    page_contents: list[str],
    max_tokens: int = 8000,
) -> str:
    """Assemble context by priority; truncate low-priority content when over budget."""
    core = f"{system_prompt}\n\nUser task: {task}"
    budget = max_tokens - estimate_tokens(core)
    if budget <= 0:
        return core[: max_tokens * 2]

    # Execution log (up to 50% of remaining budget, max 4000)
    log_budget = min(int(budget * 0.5), 4000)
    log_text = compress_execution_log(execution_log, max_tokens=log_budget)
    budget -= estimate_tokens(log_text)

    # Page contents (up to 30% of remaining budget)
    content_budget = int(budget * 0.3)
    content_parts = []
    for pc in reversed(page_contents):
        chunk = pc[:content_budget * 2]
        if not chunk:
            break
        content_parts.insert(0, chunk)
    content_text = "\n---\n".join(content_parts) if content_parts else ""
    budget -= estimate_tokens(content_text)

    # Messages (remaining budget)
    msg_parts = []
    max_msgs = getattr(settings, 'max_messages_count', 50)
    for msg in reversed(messages[-max_msgs:]):
        msg_content = getattr(msg, "content", str(msg))
        if isinstance(msg_content, list):
            msg_content = str(msg_content[0]) if msg_content else ""
        chunk = msg_content[: max(budget * 2, 200)]
        if not chunk:
            break
        msg_parts.insert(0, chunk)

    parts = [core, log_text]
    if content_text:
        parts.append(f"Page contents:\n{content_text}")
    return "\n\n".join(parts)


def _extract_page_contents(execution_log: list) -> list[str]:
    """Extract page content strings from execution log for answer context."""
    contents = []
    for entry in execution_log:
        result = entry.get("result", {})
        if isinstance(result, dict):
            text = result.get("result", result.get("content", ""))
            if isinstance(text, str) and len(text) > 20:
                contents.append(text[:1000])
    return contents


async def answer_node(state: AgentState) -> dict:
    """Prepare answer messages. Actual LLM streaming happens in main.py."""
    logger.info("[answer_node] Preparing answer context...")

    if not state.get("execution_log"):
        # No execution happened: chitchat or knowledge_qa direct path
        recent_messages = (state.get("messages") or [])[-10:]
        answer_messages = [
            SystemMessage(content="You are BrowsePilot, a helpful AI assistant skilled in browser automation. Answer the user's question directly and concisely."),
            *recent_messages,
            HumanMessage(content=state["task"]),
        ]
    else:
        # browser_task path: use compressed execution context
        page_contents = _extract_page_contents(state["execution_log"])

        system_prompt = "You are BrowsePilot. Based on the browser execution results below, answer the user's question."
        stop_reason = state.get("stop_reason", "")
        if stop_reason:
            system_prompt += (
                f"\n\n注意：本次任务因以下原因被中断，未完整执行所有步骤——{stop_reason}。"
                "请在回答开头向用户说明此情况（用自然的语言描述原因），"
                "然后根据已收集到的信息尽最大努力回答用户的问题。"
            )

        context = build_context_with_budget(
            system_prompt=system_prompt,
            task=state["task"],
            messages=state.get("messages", []),
            execution_log=state["execution_log"],
            page_contents=page_contents,
        )
        answer_messages = [SystemMessage(content=context)]

    # Store prepared messages — main.py will stream the LLM response
    return {
        "answer_messages": answer_messages,
    }


def get_answer_messages(state: AgentState) -> list:
    """Get the prepared answer messages from state for streaming in main.py."""
    return state.get("answer_messages", [])
