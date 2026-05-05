# BrowsePilot Vue3 前端重构 + 会话管理增强 设计文档

**日期:** 2026-05-05
**状态:** 已确认

---

## 1. 概述

将 BrowsePilot 前端从 Streamlit 迁移至 Vue 3，同时补充后端会话管理 API。Streamlit 代码全部保留不动，新前端作为独立项目平行运行。

**目标:**
- 解决 Streamlit 的布局/样式/性能问题（rerun 模型导致）
- 建立标准前后端分离架构，匹配企业级 Demo 定位
- 补充完整的会话管理功能（新建、列表、回放含文本、删除）

---

## 2. 技术栈

| 层 | 选型 |
|-----|------|
| 框架 | Vue 3.4+ (Composition API + `<script setup>`) |
| 构建 | Vite 6 |
| UI 组件库 | Element Plus |
| 样式 | Tailwind CSS + Element Plus 主题覆写 |
| 状态管理 | Pinia |
| 路由 | Vue Router 4（预留，一期单页） |
| HTTP | fetch + ReadableStream（原生 SSE 消费） |
| 语言 | TypeScript |

---

## 3. 目录结构

```
frontend-vue/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── api/
│   │   └── chat.ts              # SSE + REST 封装
│   ├── stores/
│   │   ├── chat.ts              # 聊天消息、SSE 事件处理
│   │   └── session.ts           # 会话列表、当前 session_id
│   ├── components/
│   │   ├── Sidebar.vue
│   │   ├── ChatPanel.vue
│   │   ├── ChatMessage.vue
│   │   ├── ThinkingIndicator.vue
│   │   ├── ChatInput.vue
│   │   ├── MonitorPanel.vue
│   │   ├── PlanSteps.vue
│   │   ├── TokenCounter.vue
│   │   ├── ScreenshotViewer.vue
│   │   ├── ReplayPanel.vue
│   │   └── SessionList.vue
│   ├── composables/
│   │   └── useSSE.ts
│   └── types/
│       └── index.ts
```

---

## 4. 设计系统（沿用 Swiss Editorial）

```
颜色令牌:
  bg:          #faf9f6
  surface:     #fefdfb
  border:      #d4cdc2
  card-border: #e8e0d4
  text-primary:#1a1a1a
  text-body:   #4a4238
  text-muted:  #8b7f6e
  text-disabled:#c4b5a5
  accent:      #e33e2b

字体:    Georgia, 'Times New Roman', serif
卡片:    border-radius: 0, 1px solid
```

---

## 5. 组件架构

```
App.vue
├── Sidebar.vue               ← 会话列表 + 新建会话 + API 配置
├── ChatPanel.vue             ← 左侧 70%
│   ├── ChatMessage.vue × N
│   ├── ThinkingIndicator.vue ← 阶段指示 + 进度条 + 动画圆点
│   └── ChatInput.vue         ← processing 时隐藏
│
└── MonitorPanel.vue          ← 右侧 30%
    ├── PlanSteps.vue         ← done/current/pending 步骤样式
    ├── TokenCounter.vue      ← 输入/输出/总计
    ├── ScreenshotViewer.vue  ← live-dot 动画 + max-h 限制
    └── ReplayPanel.vue       ← 会话选择 + 步骤回放含文本
```

---

## 6. 数据流

```
Pinia Store (单一数据源)
  ├── chatStore  ← SSE 事件写入，所有组件读取
  └── sessionStore ← 会话列表、当前会话

ChatPanel → POST /chat/stream (SSE)
         → reader.read() 逐帧解析
         → dispatch(event) 更新 store
         → 组件响应式更新（无 st.rerun）

ReplayPanel → GET /sessions (会话列表)
            → GET /replay/{id} (回放数据)

Sidebar → DELETE /sessions/{id} (删除会话)
```

---

## 7. 状态管理

### chatStore

```typescript
{
  messages: { role, content }[]
  processing: boolean
  phase: 'planning'|'executing'|'reflecting'|'replanning'|'answering'|null
  phaseMessage: string
  planSteps: string[]
  currentStepIndex: number
  screenshot: string | null
  promptTokens: number
  completionTokens: number
  sessionId: string | null
  error: string | null
}
```

Actions: `reset()`, `dispatchEvent(SSEEvent)`

### sessionStore

```typescript
{
  sessions: { id, task_summary, created_at, status }[]
  currentSessionId: string | null
}
```

Actions: `fetchList()`, `setCurrent(id)`, `removeSession(id)`

---

## 8. SSE 事件处理

现有10种事件类型全部保留，新增 `session_created`：

| 事件 | 处理 |
|------|------|
| `session_created` | **新增**，写入 `chatStore.sessionId` |
| `thinking_status` | 更新 phase, phaseMessage, stepIndex |
| `plan_generated` | 更新 planSteps, totalSteps |
| `step_start` | 更新 currentStepIndex |
| `screenshot` | 更新 screenshot (base64) |
| `step_end` | 更新进度 |
| `reflection` | 更新 phase |
| `replan` | 替换 planSteps |
| `token_update` | 更新 token 计数 |
| `final_answer` | push assistant 消息，清空 phase |
| `error` | push 错误消息 |

未知 event_type 静默忽略。

---

## 9. 错误处理

| 情形 | 处理 |
|------|------|
| fetch 连接失败 | 错误提示 2 秒消失，不阻塞输入 |
| 请求超时 | AbortController 信号，保留已执行步骤 |
| SSE 流中断 | 已收集内容作为部分回答展示 |
| HTTP 500 | 显示后端错误 + 保留输入可重试 |
| JSON 解析失败 | 跳过该帧，不中断流 |
| 空消息提交 | 输入按钮置灰 |
| 长文本/大截图 | max-height + overflow 限制 |

---

## 10. 后端 API 改动

### SSE 新增事件

```
session_created → { session_id }
```

位置：SSE 流首事件

### REST 修改/新增

| 端点 | 改动 | 返回值 |
|------|------|--------|
| `GET /sessions` | 修改 | `[{id, task_summary, created_at, status}]` |
| `GET /replay/{id}` | 修改 | 每步增加 `result` 字段（文本内容） |
| `DELETE /sessions/{id}` | 新增 | `{"ok": true}` 或 404 |

### 涉及文件

- `backend/app/events.py` — +3 行
- `backend/app/main.py` — +20 行
- `backend/app/session_manager.py` — +15 行

---

## 11. 部署

- 前端：`npm run build` → 静态文件，Nginx 托管
- 后端：`uvicorn backend.app.main:app`（不变）
- MCP：`python -m browser_mcp.main`（不变）
- 推荐 Linux 云主机部署，三个进程由 systemd 或 docker-compose 管理
