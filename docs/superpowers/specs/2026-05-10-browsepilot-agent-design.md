# BrowsePilot Agent 流程改造 — 实现规范

## 概述

本规范覆盖 A 层 5 项需求：意图分类路由（#3）、execute 重试修复（#2）、Agent 五节点优化（#4）、健壮性加固（#7）、Token 统计与上下文管理（#8）。

**设计约束**：SMALL_MODEL/BIG_MODEL 分离，共享凭据可覆盖，LLM 超时重试 1 次后降级，messages 字段苏醒，llm_vision_enabled 控制视觉传入。

---

## 一、模型配置重构

### 1.1 .env 配置格式

```env
# 共享凭据（默认值，被各模型 fallback 使用）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1

# 大模型（主流程：plan/execute/reflect/replan/answer）
BIG_MODEL=deepseek-v4-flash
# BIG_MODEL_API_KEY=sk-yyy    # 可选：覆盖共享凭据
# BIG_MODEL_BASE_URL=...      # 可选：覆盖共享凭据

# 小模型（classify 分类节点）
SMALL_MODEL=deepseek-chat
# SMALL_MODEL_API_KEY=sk-zzz  # 可选：覆盖共享凭据
# SMALL_MODEL_BASE_URL=...    # 可选：覆盖共享凭据

# 视觉能力
LLM_VISION_ENABLED=false
```

### 1.2 config.py 对应字段

```
openai_api_key: str       # 共享
openai_base_url: str      # 共享

big_model: str            # 必需
big_model_api_key: str    # 空=fallback 共享
big_model_base_url: str   # 空=fallback 共享

small_model: str          # 必需
small_model_api_key: str  # 空=fallback 共享
small_model_base_url: str # 空=fallback 共享

llm_vision_enabled: bool  # 已有
```

### 1.3 get_llm() / get_small_llm()

```python
def get_llm():
    return ChatOpenAI(
        model=settings.big_model,
        api_key=settings.big_model_api_key or settings.openai_api_key,
        base_url=settings.big_model_base_url or settings.openai_base_url,
    )

def get_small_llm():
    return ChatOpenAI(
        model=settings.small_model,
        api_key=settings.small_model_api_key or settings.openai_api_key,
        base_url=settings.small_model_base_url or settings.openai_base_url,
    )
```

---

## 二、意图分类路由（#3）

### 2.1 图结构变更

```
START → classify
          ├─ chitchat ──────────→ answer → END
          ├─ knowledge_qa ──────→ answer → END
          └─ browser_task → (MCP lazy connect) → plan → execute → ...
```

入口从 `plan` 改为 `classify`，条件路由 `_route_classify` 根据 `state["intent"]` 分流。

### 2.2 classify_node

使用 `get_small_llm()`，以完整分类 prompt 识别意图：

```
你是一个意图分类器。分析用户的输入，判断其意图属于以下哪一种：

1. chitchat — 闲聊、打招呼、与浏览器操作无关的对话
   示例：
   - "你好" / "你是谁" / "今天天气怎么样"
   - "谢谢你" / "再见"

2. knowledge_qa — 需要知识回答的问题，不需要浏览器操作
   示例：
   - "介绍一下机器学习分类方法"
   - "Python 的 GIL 是什么"
   - "比较 React 和 Vue 的优缺点"

3. browser_task — 需要打开浏览器执行具体操作的任务
   示例：
   - "打开百度搜索 LangChain"
   - "帮我在 GitHub 上找 Python 爬虫项目"
   - "看看百度首页有什么内容"

规则：
- 如果用户只是聊天、问候或问你是谁 → chitchat
- 如果用户需要知识解答但不需要浏览器操作 → knowledge_qa
- 如果用户需要打开网页、点击、输入、截图等浏览器操作 → browser_task

返回 JSON 格式：{"intent": "chitchat|knowledge_qa|browser_task"}
只返回 JSON，不要包含任何其他内容。
```

### 2.3 MCP 延迟连接

- `main.py` 中移除 graph 构建前的 `mcp_client.connect()` 调用
- MCPClient 对象创建后不立即连接
- graph 的 plan wrapper 中检查 `mcp_client.is_connected`，未连接则调用 `connect()`
- chitchat / knowledge_qa 路径全程不连接 MCP

### 2.4 改动文件

| 文件 | 改动 |
|------|------|
| `backend/app/agent/graph.py` | 新增 classify 节点 + 条件路由 + plan wrapper 中 lazy MCP |
| `backend/app/agent/nodes.py` | 新增 classify_node + get_small_llm() |
| `backend/app/agent/state.py` | +intent 字段 |
| `backend/app/main.py` | 移除 eager MCP 连接 |
| `backend/app/config.py` | 模型配置重构 |
| `.env` / `.env.example` | LLM_MODEL → SMALL_MODEL + BIG_MODEL |

---

## 三、execute 重试修复（#2）

### 3.1 步骤弹出逻辑

```python
# execute_node 中
result = await mcp_client.call_tool(tool_name, arguments)
success = result.get("status") != "error"

if success:
    new_plan = state["plan"][1:]   # 弹出当前步骤
    return {"plan": new_plan, "retry_count": 0, ...}
else:
    # 失败：保留当前步骤，等待 reflect 判重试
    return {"plan": state["plan"], "retry_count": state["retry_count"] + 1, ...}
```

### 3.2 行为表

| 场景 | 行为 |
|------|------|
| 步骤成功 | 弹出，retry_count 清零，继续下一步 |
| 步骤失败，retry_count < 2 | 保留在 plan 中，reflect 判重试 |
| 步骤失败，retry_count >= 2 | reflect 判 replan |

### 3.3 改动文件

仅 `backend/app/agent/nodes.py` — `execute_node` 函数。

---

## 四、Agent 五节点优化（#4）

### 4.1 reflect_node：两级反思

**级别一（启发式检查，代码级，零成本）**：

| 检查项 | 方法 | 阈值 | 不通过时 |
|--------|------|------|---------|
| 页面内容过短 | get_content 返回文字数 | < 50 字 | 触发级别二 |
| 域名突变 | 当前 URL vs 预期域名 | 域名变化 | 触发级别二 |
| 连续相似结果 | execution_log 末尾 3 条比较 | 相似度 > 80% | 标记停滞 → 触发级别二 |
| 页面元素过少 | get_page_structure 返回元素数 | inputs + buttons < 3 | 触发级别二 |

**级别二（LLM 深度反思，两处触发）**：

| 触发时机 | 行为 |
|---------|------|
| 步骤失败 或 级别一未通过 | LLM 分析原因，决定 retry / replan / answer |
| plan 为空（完工检查） | LLM 检查已收集信息是否足以回答用户，不足则生成 1-3 补充步骤回填 plan |

完工检查 prompt：
```
用户问题：{task}
已执行步骤及结果：{execution_log 摘要}
收集到的页面内容：{page_contents 截断}

当前信息是否足以回答用户的问题？
- 足 → {"action": "answer"}
- 不足 → {"action": "continue", "extra_steps": ["补充步骤1", ...]}
  最多 3 个补充步骤。
```

### 4.2 plan_node：自检

生成计划后，追加一次简短 LLM 调用：
```
用户任务：{task}
已生成的计划：{initial_plan}

这个计划执行完毕后，获得的信息能否回答用户的原始问题？
如果不能，请在计划末尾补充缺失的步骤。
返回 JSON：{"sufficient": true/false, "extra_steps": [...]}
```

若 insufficient，将 extra_steps 追加到 plan 末尾。

### 4.3 replan_node：视觉接入

严格受 `llm_vision_enabled` 控制：

```
if llm_vision_enabled == True:
    读取 execution_log 中失败步骤的 screenshot_path
    将截图 base64 编码传入 LLM（多模态消息）
else:
    仅传文本上下文，不读截图、不编码、不传入
```

硬性约束：
- 必须从 `settings.llm_vision_enabled` 读取
- 即使 screenshot_path 存在，`False` 时也不编码不传入，防止向不支持视觉的模型发送无意义数据

### 4.4 execute_node：精简 prompt

从 ~30 行压缩到 ~15 行，去掉重复规则：
```
你是浏览器自动化执行专家。
可用工具：{tools_desc}

核心规则：
1. 操作页面元素前，必须先用 get_page_structure 获取实际选择器
2. 只使用页面结构中返回的选择器，禁止编造或猜测
3. 一次只执行一个操作

最近执行上下文：
{recent_context}
```

保留 `recent_context` 提取逻辑（已验证有效）。

### 4.5 answer_node：边界兜底

```python
if not state.get("execution_log"):
    # chitchat / knowledge_qa 直通：基于 messages + task 直接回答
    response = await llm.ainvoke([
        SystemMessage("你是一个有用的AI助手。"),
        *state["messages"][-10:],
        HumanMessage(state["task"]),
    ])
else:
    # browser_task：基于压缩执行日志生成回答
    context = build_context_with_budget(ANSWER_PROMPT, task, messages, execution_log, page_contents)
    response = await llm.ainvoke([SystemMessage(context)])
```

---

## 五、健壮性加固（#7）

### 5.1 熔断器

AgentState 新增 3 个计数器：

| 计数器 | 触发条件 | 阈值 | 行为 |
|--------|---------|------|------|
| `consecutive_failures` | result.status == "error" | >= 3 | 跳过剩余步骤 → answer |
| `stagnation_count` | 末尾 3 条结果相似度 > 80% | >= 3 | 标记停滞，reflect 提示换策略 |
| `replan_count` | 每次进入 replan_node | >= 2 | 放弃 → answer（部分结果） |

### 5.2 重复 plan 检测

```python
def compute_plan_similarity(old_plan: list[str], new_plan: list[str]) -> float:
    """Jaccard 相似度，中文按字、英文按词切分。不调 LLM。"""
    def tokenize(steps):
        tokens = set()
        for s in steps:
            for word in s.replace(" ", ""):
                tokens.add(word)
        return tokens
    old_tokens = tokenize(old_plan)
    new_tokens = tokenize(new_plan)
    if not old_tokens or not new_tokens:
        return 0.0
    return len(old_tokens & new_tokens) / len(old_tokens | new_tokens)
```

边界：
- = 1.0 → 完全相同，放弃，need_replan=False → answer
- > 0.8 → 高度相似，stagnation_count +1，reflect 提示注入警告
- <= 0.8 → 通过，stagnation_count 清零

reflect 注入警告文本：
```
⚠ 重要警告：上一轮重规划生成的计划与旧计划高度相似（相似度 > 80%）。
当前策略可能陷入了死循环。请尝试从根本上不同的替代方案：
- 改变操作顺序
- 尝试不同的导航路径
- 如果当前页面无法完成任务，考虑回退到搜索引擎重新开始
如果确实没有可行的替代方案，请直接判定 answer。
```

### 5.3 超时保护

| 位置 | 措施 | 超时 | 超时行为 |
|------|------|------|---------|
| MCP call_tool | `asyncio.wait_for` | 30s | → {status:"error", error:"timeout"} → reflect |
| LLM ainvoke（所有节点） | `asyncio.wait_for` | 60s | 重试 1 次 → 仍超时走降级 |
| Session graph.astream | `asyncio.wait_for` | 300s | 返回部分结果 + 持久化 |
| 无超时 MCP 工具（get_content, get_page_structure, screenshot, scroll） | browser_mcp 工具内 wait_for | 15-30s | → error 返回 |

LLM 超时降级策略：

| 节点 | 降级行为 |
|------|---------|
| plan | 使用默认计划：["导航到目标网站", "获取页面内容", "回答用户"] |
| execute | 跳过当前步骤，标记 timeout |
| reflect | 默认判 answer |
| replan | 直接 answer |
| answer | 返回原始收集信息摘要 |

### 5.4 recursion_limit 降级

`_route_reflect` 中增加预警：step_count >= 25 时强制路由到 answer，避免触发 GraphRecursionError。answer 内容包含"部分结果"提示。

step_count 通过 `len(state["execution_log"])` 获取。

### 5.5 资源清理加固

| 场景 | 改为 |
|------|------|
| 异常时会话持久化 | `except` 块中调用 `session_manager.persist(session_id)` |
| MCP close 异常 | `try/except` → 至少 `logger.warning` |
| 截图清理 | 纳入 SessionManager TTL 清理（联动 #6） |
| LLM JSON 解析失败 | 重试 1 次 → 仍失败记录原因走降级 |

### 5.6 改动文件

| 文件 | 改动 |
|------|------|
| `backend/app/agent/state.py` | +consecutive_failures, stagnation_count, replan_count |
| `backend/app/agent/nodes.py` | 各节点超时包裹 + 熔断检测 + 重复 plan 检测 |
| `backend/app/agent/graph.py` | recursion_limit 预警路由 |
| `backend/app/mcp_client.py` | call_tool 超时（联动 #5） |
| `backend/app/main.py` | session 超时 + 异常持久化 |
| `backend/app/config.py` | 超时/熔断阈值配置 |
| `browser_mcp/tools/` | 4 个无超时工具增加 wait_for |

---

## 六、Token 统计与上下文管理（#8）

### 6.1 Token 覆盖修复

6 个调用 LLM 的节点（classify, plan, execute, reflect, replan, answer）全部通过 `accumulate_tokens()` 提取 `usage_metadata` 并累加。

```python
def accumulate_tokens(current: dict, response, node_name: str) -> dict:
    usage = response.usage_metadata
    if not usage:
        return current
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
```

AgentState 中 token_usage 结构：
```python
token_usage: {
    "prompt": 0,         # 全程累加
    "completion": 0,     # 全程累加
    "breakdown": {       # 按节点分项
        "classify": {"prompt": 0, "completion": 0},
        "plan":     {...},
        ...
    },
}
```

### 6.2 双层上下文截断

**内层** — `compress_execution_log(execution_log, max_tokens=4000)`：
最近 3 步完整保留，更早步骤只保留步骤名 + 成功/失败。

**外层** — `build_context_with_budget(system_prompt, task, messages, execution_log, page_contents, max_tokens=8000)`：

按优先级从高到低组装：

| 优先级 | 内容 | 裁切策略 |
|--------|------|---------|
| 1（保留） | system_prompt + task | 不裁切（极端情况按字符截断） |
| 2 | execution_log（已压缩） | 内层压缩，外层限制占总 budget 50% |
| 3 | messages | 从最旧的开始丢弃，单条 > 200 字截断 |
| 4（先裁） | page_contents | 每页截断到 500 字，超出时丢弃最早页面 |

Token 估算使用保守的 `len(text) // 2`。

### 6.3 messages 字段苏醒

answer_node 中 messages 作为对话上下文传入（chitchat/knowledge_qa 路径最近 10 条，browser_task 路径通过 `build_context_with_budget` 控制）。

### 6.4 三个缺陷修复

| 缺陷 | 修复 |
|------|------|
| LangChain Tool 架空 | 移除 `tools.py` 的 langchain_tools 转换层，直接从 mcp_client.tools 生成工具描述文本 |
| 截图序号冲突 | AgentState 新增 `total_steps: int` 单调递增计数器，截图文件以此命名 |
| accumulated_state 脆弱 | 改为使用 graph.astream 每次 emit 的完整 state，或最后 graph.ainvoke 获取最终状态 |

### 6.5 改动文件

| 文件 | 改动 |
|------|------|
| `backend/app/agent/state.py` | token_usage 累加结构 + total_steps |
| `backend/app/agent/nodes.py` | 6 节点全部调用 accumulate_tokens + 日志压缩 + 截图序号用 total_steps |
| `backend/app/agent/graph.py` | 无直接改动（token 在各节点内部处理） |
| `backend/app/config.py` | MAX_CONTEXT_TOKENS, MAX_MESSAGES_COUNT |
| `backend/app/agent/tools.py` | 移除 langchain_tools 转换层 |
| `backend/app/main.py` | SSE token_update 适配新累加结构 + accumulated_state 修复 |

---

## 七、AgentState 最终字段

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    intent: str                          # 新增：classify 结果
    plan: list[str]
    execution_log: list[dict]
    retry_count: int
    need_replan: bool
    final_answer: str
    total_steps: int                     # 新增：单调递增截图计数器
    token_usage: dict                    # 改为累加结构
    consecutive_failures: int            # 新增：熔断计数器
    stagnation_count: int                # 新增：停滞计数器
    replan_count: int                    # 新增：重规划计数器
    stagnation_warning: bool             # 新增：reflect 提示注入开关
    completion_check_count: int          # 新增：完工检查次数限制（最多1次）
```

---

## 八、A 层文件总览

```
backend/app/
├── config.py                  ← 模型配置重构 + 超时/熔断/上下文配置
├── agent/
│   ├── state.py               ← +7 个字段（含 token_usage 改造）
│   ├── graph.py               ← classify 节点 + 条件路由 + lazy MCP + recursion_limit 预警
│   ├── nodes.py               ← 6 节点全部改动（核心）
│   └── tools.py               ← 移除 langchain_tools 转换层
├── main.py                    ← 移除 eager MCP + session 超时 + 异常持久化 + state 修复
├── mcp_client.py              ← call_tool 超时（联动 #5）
└── session_manager.py         ← 无直接改动
browser_mcp/tools/             ← 4 个工具 +wait_for
.env / .env.example            ← 模型配置重构
```

## 九、与 B+C 层的联动点

1. **config.py**：B+C 的显式加载 + 校验 与 A 层的模型配置重构合并到同一个 config.py
2. **mcp_client.py**：B+C 的 transport 改造 + 加固 与 A 层的 call_tool 超时合并
3. **browser_mcp/tools/**：A 层 4 个工具的超时 与 B+C 层无关，独立改动
4. **session_manager.py**：B+C 的数据清理 + 并发限制已定稿，A 层不追加变更
5. **main.py**：B+C 层无改动，A 层改动（lazy MCP + session 超时 + 异常持久化 + state 修复）

## 十、风险与注意事项

1. **classify 误分类**：小模型可能将 browser_task 误判为 knowledge_qa，导致用户任务丢失。需记录 classify 结果到 execution_log，便于排查。可考虑在 answer_node 加一道检查——如果 messages 中用户明确要求浏览器操作但 intent 非 browser_task，追加一次确认
2. **MCP lazy connect 失败**：classify 判为 browser_task 后，MCP 连接可能失败（browser-mcp 未启动）。应返回友好提示而非 500
3. **完工检查可能形成循环**：reflect 判"不足"→ 补充步骤 → 执行 → 再次完工检查 → 再判"不足"。AgentState 新增 `completion_check_count: int`，完工检查最多触发 1 次。第二次 plan 为空时直接路由 answer，不再补充步骤
4. **total_steps 溢出**：理论上 int 无上限，但长时间运行的大量步骤任务本身就是问题（会被熔断器或 recursion_limit 拦截）
5. **accumulate_tokens 跨会话污染**：需确保每个 session 初始化时 token_usage 从零开始（当前 main.py 的 initial_state 已保证）
