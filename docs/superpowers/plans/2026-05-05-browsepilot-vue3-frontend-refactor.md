# BrowsePilot Vue3 前端重构 + 会话管理增强 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 BrowsePilot 前端从 Streamlit 迁移至 Vue3，同时补充后端会话管理 API（新建/列表/回放含文本/删除），保留原有 Swiss Editorial 设计风格。

**Architecture:** 后端新增 `session_created` SSE 事件 + 3 个 REST 端点改动（共 ~40 行）。前端替换为 Vue3 SPA，通过 Pinia store + useSSE composable 消费现有 SSE 流，组件响应式更新替代 `st.rerun()`。

**Tech Stack:** Vue 3.4+ (Composition API), Vite 6, TypeScript, Pinia, Element Plus, Tailwind CSS 3, FastAPI (后端改动)

---

## 文件结构总览

```
# 后端改动（3 文件）
backend/app/events.py          — 修改：+1 方法
backend/app/session_manager.py — 修改：+2 方法
backend/app/main.py            — 修改：+3 端点改动

# 前端新建（16 文件）
frontend-vue/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── postcss.config.js
├── tailwind.config.js
├── env.d.ts
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── style.css
│   ├── api/
│   │   └── chat.ts
│   ├── stores/
│   │   ├── chat.ts
│   │   └── session.ts
│   ├── composables/
│   │   └── useSSE.ts
│   ├── types/
│   │   └── index.ts
│   └── components/
│       ├── Sidebar.vue
│       ├── ChatPanel.vue
│       ├── ChatMessage.vue
│       ├── ThinkingIndicator.vue
│       ├── ChatInput.vue
│       ├── MonitorPanel.vue
│       ├── PlanSteps.vue
│       ├── TokenCounter.vue
│       ├── ScreenshotViewer.vue
│       └── ReplayPanel.vue
```

---

### Task 1: 新增 `session_created` SSE 事件

**Files:**
- Modify: `backend/app/events.py:46-48`

- [ ] **Step 1: 在 SSEData 类中添加 session_created 静态方法**

```python
# backend/app/events.py，在 error 方法之后追加：
@staticmethod
def session_created(session_id: str) -> dict:
    return {"event": "session_created", "data": {"session_id": session_id}}
```

- [ ] **Step 2: 验证语法**

Run: `python -c "from backend.app.events import SSEData; print(SSEData.session_created('abc12345'))"`
Expected: `{'event': 'session_created', 'data': {'session_id': 'abc12345'}}`

- [ ] **Step 3: Commit**

```bash
git add backend/app/events.py
git commit -m "feat: add session_created SSE event type"
```

---

### Task 2: SessionManager 新增 delete 方法 + list_sessions 返回摘要

**Files:**
- Modify: `backend/app/session_manager.py:75-89`

- [ ] **Step 1: 重写 list_sessions 返回摘要**

```python
# backend/app/session_manager.py，替换原有 list_sessions 方法（行 75-79）：
def list_sessions(self) -> list[dict]:
    """返回会话列表，每个会话含 id、task 摘要、创建时间、状态。"""
    sessions_dir = Path(f"{settings.data_dir}/sessions")
    if not sessions_dir.exists():
        return []
    results = []
    for f in sorted(sessions_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append({
                "id": data.get("session_id", f.stem),
                "task_summary": (data.get("task", "") or "")[:30],
                "created_at": data.get("created_at", ""),
                "status": data.get("status", "unknown"),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return results
```

- [ ] **Step 2: 在 SessionManager 类中添加 delete 方法**

```python
# backend/app/session_manager.py，在 list_sessions 方法之后添加：
def delete_session(self, session_id: str) -> bool:
    """删除会话持久化文件。返回 True 表示删除成功。"""
    filepath = Path(f"{settings.data_dir}/sessions/{session_id}.json")
    if filepath.exists():
        filepath.unlink()
        logger.info("Session {} deleted", session_id)
        return True
    return False
```

- [ ] **Step 3: 运行已有测试确认不引入回归**

Run: `pytest browser_mcp/tools/test_security.py -v`
Expected: 19 passed

- [ ] **Step 4: Commit**

```bash
git add backend/app/session_manager.py
git commit -m "feat: add session delete + list_sessions returns summaries"
```

---

### Task 3: 更新 main.py 端点 + 首事件

**Files:**
- Modify: `backend/app/main.py:47-57, 85-89, 184-186`

- [ ] **Step 1: 在 SSE 流首部发送 session_created 事件**

在 `backend/app/main.py` 的 `event_generator()` 函数中，`try:` 块内 `accumulated_state = dict(initial_state)` 之后添加：

```python
# 行 80 之后插入：
yield SSEData.session_created(session_id)
```

- [ ] **Step 2: 修改 GET /sessions 端点返回摘要**

```python
# backend/app/main.py，替换行 184-186：
@app.get("/sessions")
async def list_sessions():
    return JSONResponse(content=session_manager.list_sessions())
```

- [ ] **Step 3: 修改 GET /replay/{id} 返回每步文本结果**

```python
# backend/app/main.py，替换 get_replay 函数（行 178-181）：
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
```

- [ ] **Step 4: 添加 DELETE /sessions/{id} 端点**

```python
# backend/app/main.py，在 list_sessions 函数之后、health 函数之前（行 186 之后）添加：
@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    ok = session_manager.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return JSONResponse(content={"ok": True})
```

- [ ] **Step 5: 手动测试后端**

启动后端：
```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

验证 4 个端点：
```bash
# 1. GET /sessions 返回摘要格式
curl -s http://localhost:8000/sessions | python -m json.tool

# 2. Health 正常
curl -s http://localhost:8000/health

# 3. DELETE 不存在的会话返回 404
curl -s -X DELETE http://localhost:8000/sessions/nonexistent

# 4. SSE 流包含 session_created 首事件
curl -s -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"task":"test"}' | head -4
# 第一条 data 应包含 "session_created"
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: add session_created SSE event, DELETE endpoint, replay text results"
```

---

### Task 4: 创建 Vue3 项目脚手架

**Files:**
- Create: `frontend-vue/package.json`
- Create: `frontend-vue/index.html`
- Create: `frontend-vue/vite.config.ts`
- Create: `frontend-vue/tsconfig.json`
- Create: `frontend-vue/tsconfig.node.json`
- Create: `frontend-vue/postcss.config.js`
- Create: `frontend-vue/tailwind.config.js`
- Create: `frontend-vue/env.d.ts`
- Create: `frontend-vue/src/main.ts`
- Create: `frontend-vue/src/style.css`
- Create: `frontend-vue/src/App.vue`（占位）

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "browsepilot-vue",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.5.0",
    "pinia": "^2.1.0",
    "element-plus": "^2.9.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2.0",
    "typescript": "^5.7.0",
    "vite": "^6.0.0",
    "vue-tsc": "^2.2.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "@types/node": "^22.0.0"
  }
}
```

- [ ] **Step 2: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>BrowsePilot</title>
  </head>
  <body style="margin:0;background:#faf9f6">
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 3: 创建 vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
```

- [ ] **Step 4: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "noEmit": true,
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.d.ts", "src/**/*.vue", "env.d.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 5: 创建 tsconfig.node.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "composite": true,
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: 创建 postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 7: 创建 tailwind.config.js（含 Swiss Editorial 设计令牌）**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,js}'],
  theme: {
    extend: {
      colors: {
        bg: '#faf9f6',
        surface: '#fefdfb',
        border: '#d4cdc2',
        'card-border': '#e8e0d4',
        'text-primary': '#1a1a1a',
        'text-body': '#4a4238',
        'text-muted': '#8b7f6e',
        'text-disabled': '#c4b5a5',
        accent: '#e33e2b',
      },
      fontFamily: {
        serif: ['Georgia', '"Times New Roman"', 'serif'],
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 8: 创建 env.d.ts**

```typescript
/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
```

- [ ] **Step 9: 创建 src/main.ts（占位）**

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import App from './App.vue'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus)
app.mount('#app')
```

- [ ] **Step 10: 创建 src/style.css（全局样式 + Element Plus 主题覆写）**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Element Plus 主题覆写 — Swiss Editorial */
:root {
  --el-font-family: Georgia, 'Times New Roman', serif;
  --el-border-color: #e8e0d4;
  --el-bg-color: #fefdfb;
  --el-text-color-regular: #4a4238;
  --el-text-color-secondary: #8b7f6e;
  --el-border-radius-base: 0px;
}

/* 全局 */
html, body, #app {
  height: 100vh;
  overflow: hidden;
  background-color: #faf9f6;
  font-family: Georgia, 'Times New Roman', serif;
  color: #4a4238;
}

/* 动画 */
@keyframes fadeInOut {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.live-dot {
  display: inline-block;
  width: 5px; height: 5px;
  background: #e33e2b;
  border-radius: 50%;
  animation: fadeInOut 1.5s ease-in-out infinite;
}

.thinking-dot {
  display: inline-block;
  width: 4px; height: 4px;
  background: #e33e2b;
  border-radius: 50%;
  animation: fadeInOut 1s ease-in-out infinite;
  vertical-align: middle;
  margin-left: 6px;
}

/* Phase label */
.phase-label {
  font-size: 10px;
  color: #8b7f6e;
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-bottom: 6px;
  font-family: Georgia, serif;
}

/* Progress bar */
.progress-bar {
  display: flex;
  gap: 3px;
  margin-top: 8px;
}
.progress-segment {
  height: 3px;
  flex: 1;
  background: #e8e0d4;
}
.progress-segment.done {
  background: #e33e2b;
}
.progress-segment.active {
  background: #e33e2b;
  animation: fadeInOut 1s ease-in-out infinite;
}

/* Plan step */
.plan-step { line-height: 2; font-size: 12px; }
.plan-step.done { color: #c4b5a5; text-decoration: line-through; }
.plan-step.current {
  color: #e33e2b;
  font-weight: 600;
  font-style: italic;
  border-left: 2px solid #e33e2b;
  padding-left: 8px;
}
.plan-step.pending { color: #8b7f6e; }
```

- [ ] **Step 11: 创建 src/App.vue（占位，验证项目运行）**

```vue
<template>
  <div class="flex h-screen bg-bg font-serif text-text-body">
    <p class="m-auto text-text-muted italic">BrowsePilot — 加载中...</p>
  </div>
</template>

<script setup lang="ts">
</script>
```

- [ ] **Step 12: 安装依赖并验证项目启动**

```bash
cd frontend-vue
npm install
npm run dev
```

打开浏览器访问 `http://localhost:5173`，应看到占位文字。

- [ ] **Step 13: Commit**

```bash
git add frontend-vue/
git commit -m "feat: scaffold Vue3 project with Tailwind + Element Plus + Swiss design tokens"
```

---

### Task 5: TypeScript 类型定义

**Files:**
- Create: `frontend-vue/src/types/index.ts`

- [ ] **Step 1: 写入类型定义**

```typescript
// frontend-vue/src/types/index.ts

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export type AgentPhase = 'planning' | 'executing' | 'reflecting' | 'replanning' | 'answering'

export interface SSEEvent {
  event: string
  data: Record<string, any>
}

export interface SessionSummary {
  id: string
  task_summary: string
  created_at: string
  status: string
}

export interface ReplayStep {
  step_index: number
  step: string
  screenshot_path: string
  timestamp: string
  result: Record<string, any>
}

export interface ChatState {
  messages: ChatMessage[]
  processing: boolean
  phase: AgentPhase | null
  phaseMessage: string
  planSteps: string[]
  currentStepIndex: number
  totalSteps: number
  screenshot: string | null
  promptTokens: number
  completionTokens: number
  sessionId: string | null
  error: string | null
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/types/
git commit -m "feat: add TypeScript type definitions"
```

---

### Task 6: chatStore — Pinia 聊天状态管理

**Files:**
- Create: `frontend-vue/src/stores/chat.ts`

- [ ] **Step 1: 写入 chatStore**

```typescript
// frontend-vue/src/stores/chat.ts
import { defineStore } from 'pinia'
import type { ChatMessage, AgentPhase, ChatState, SSEEvent } from '@/types'

export const useChatStore = defineStore('chat', {
  state: (): ChatState => ({
    messages: [],
    processing: false,
    phase: null,
    phaseMessage: '',
    planSteps: [],
    currentStepIndex: 0,
    totalSteps: 0,
    screenshot: null,
    promptTokens: 0,
    completionTokens: 0,
    sessionId: null,
    error: null,
  }),

  getters: {
    totalTokens: (state) => state.promptTokens + state.completionTokens,
  },

  actions: {
    reset() {
      this.phase = null
      this.phaseMessage = ''
      this.planSteps = []
      this.currentStepIndex = 0
      this.totalSteps = 0
      this.screenshot = null
      this.promptTokens = 0
      this.completionTokens = 0
      this.error = null
    },

    dispatchEvent(event: SSEEvent) {
      const d = event.data
      switch (event.event) {
        case 'session_created':
          this.sessionId = d.session_id
          break

        case 'thinking_status':
          this.phase = d.phase
          this.phaseMessage = d.message || ''
          if (d.step_index) this.currentStepIndex = d.step_index
          if (d.total_steps) this.totalSteps = d.total_steps
          break

        case 'plan_generated':
          this.planSteps = d.steps || []
          this.totalSteps = this.planSteps.length
          this.phase = 'executing'
          if (d.token_usage) {
            this.promptTokens = d.token_usage.prompt || 0
            this.completionTokens = d.token_usage.completion || 0
          }
          break

        case 'step_start':
          if (d.step_index != null) {
            this.currentStepIndex = d.step_index + 1
          }
          break

        case 'screenshot':
          if (d.base64) this.screenshot = d.base64
          break

        case 'step_end':
          // 进度更新由 thinking_status 驱动
          break

        case 'reflection':
          if (d.decision === 'replan') this.phase = 'replanning'
          break

        case 'replan':
          if (d.new_steps) {
            this.planSteps = d.new_steps
            this.totalSteps = this.planSteps.length
            this.currentStepIndex = 0
          }
          break

        case 'token_update':
          this.promptTokens = d.prompt || 0
          this.completionTokens = d.completion || 0
          break

        case 'final_answer':
          this.messages.push({ role: 'assistant', content: d.content || '' })
          this.phase = null
          break

        case 'error':
          this.messages.push({ role: 'assistant', content: `❌ 错误: ${d.message || '未知错误'}` })
          break

        default:
          break
      }
    },

    addUserMessage(task: string) {
      this.messages.push({ role: 'user', content: task })
      this.processing = true
    },

    finishProcessing() {
      this.processing = false
    },
  },
})
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/stores/chat.ts
git commit -m "feat: add chatStore with SSE event dispatch"
```

---

### Task 7: sessionStore — 会话列表状态管理

**Files:**
- Create: `frontend-vue/src/stores/session.ts`

- [ ] **Step 1: 写入 sessionStore**

```typescript
// frontend-vue/src/stores/session.ts
import { defineStore } from 'pinia'
import type { SessionSummary } from '@/types'

const API_BASE = '/api'

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as SessionSummary[],
    loading: false,
  }),

  actions: {
    async fetchList() {
      this.loading = true
      try {
        const resp = await fetch(`${API_BASE}/sessions`)
        if (resp.ok) {
          this.sessions = await resp.json()
        }
      } catch {
        // 后端不可用时静默
      } finally {
        this.loading = false
      }
    },

    async deleteSession(id: string) {
      try {
        const resp = await fetch(`${API_BASE}/sessions/${id}`, { method: 'DELETE' })
        if (resp.ok) {
          this.sessions = this.sessions.filter(s => s.id !== id)
        }
      } catch {
        // 静默
      }
    },
  },
})
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/stores/session.ts
git commit -m "feat: add sessionStore with fetchList and deleteSession"
```

---

### Task 8: API 模块 + useSSE composable

**Files:**
- Create: `frontend-vue/src/api/chat.ts`
- Create: `frontend-vue/src/composables/useSSE.ts`

- [ ] **Step 1: 创建 API 模块**

```typescript
// frontend-vue/src/api/chat.ts
import type { ReplayStep } from '@/types'

const API_BASE = '/api'

export async function streamChat(
  task: string,
  sessionId: string | null,
  onEvent: (eventType: string, data: Record<string, any>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, session_id: sessionId }),
    signal,
  })

  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`后端错误 (${resp.status}): ${text}`)
  }

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      while (true) {
        const idx = buffer.indexOf('\n\n')
        if (idx === -1) break
        const frame = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)

        const lines = frame.split('\n')
        const dataLine = lines.find(l => l.startsWith('data: '))
        if (!dataLine) continue

        try {
          const event = JSON.parse(dataLine.slice(6))
          onEvent(event.event, event.data)
        } catch {
          // 跳过无法解析的帧
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function fetchReplay(sessionId: string): Promise<ReplayStep[]> {
  const resp = await fetch(`${API_BASE}/replay/${sessionId}`)
  if (!resp.ok) throw new Error(`获取回放失败 (${resp.status})`)
  return resp.json()
}

export async function fetchSessions() {
  const resp = await fetch(`${API_BASE}/sessions`)
  if (!resp.ok) throw new Error(`获取会话列表失败 (${resp.status})`)
  return resp.json()
}

export async function deleteSessionApi(id: string) {
  const resp = await fetch(`${API_BASE}/sessions/${id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`删除失败 (${resp.status})`)
  return resp.json()
}
```

- [ ] **Step 2: 创建 useSSE composable**

```typescript
// frontend-vue/src/composables/useSSE.ts
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { streamChat } from '@/api/chat'

export function useSSE() {
  const store = useChatStore()
  const errorMessage = ref('')
  let controller: AbortController | null = null

  async function startTask(task: string) {
    store.reset()
    store.addUserMessage(task)
    errorMessage.value = ''

    controller = new AbortController()

    try {
      await streamChat(
        task,
        store.sessionId,
        (eventType, data) => {
          store.dispatchEvent({ event: eventType, data })
        },
        controller.signal,
      )
    } catch (e: any) {
      if (e.name === 'AbortError') return
      const msg = e.message || '连接失败'
      if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
        store.messages.push({
          role: 'assistant',
          content: `无法连接到后端，请确认后端已启动`,
        })
      } else {
        store.messages.push({ role: 'assistant', content: `请求失败: ${msg}` })
      }
    } finally {
      store.finishProcessing()
      controller = null
    }
  }

  function cancel() {
    controller?.abort()
  }

  return { startTask, cancel, errorMessage }
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend-vue/src/api/ frontend-vue/src/composables/
git commit -m "feat: add API module and useSSE composable"
```

---

### Task 9: ChatMessage 组件

**Files:**
- Create: `frontend-vue/src/components/ChatMessage.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/ChatMessage.vue -->
<template>
  <div :class="['flex gap-3 py-3', role === 'user' ? 'justify-end' : 'justify-start']">
    <div
      :class="[
        'max-w-[80%] leading-relaxed text-[15px]',
        role === 'user'
          ? 'bg-surface border border-card-border px-3 py-2'
          : 'bg-transparent px-3 py-2',
      ]"
    >
      {{ content }}
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  role: 'user' | 'assistant'
  content: string
}>()
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/ChatMessage.vue
git commit -m "feat: add ChatMessage component"
```

---

### Task 10: ThinkingIndicator 组件

**Files:**
- Create: `frontend-vue/src/components/ThinkingIndicator.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/ThinkingIndicator.vue -->
<template>
  <div v-if="phase">
    <div class="phase-label">
      {{ label }}<span class="thinking-dot"></span>
    </div>
    <div class="font-serif text-[14px] text-text-body">{{ message }}</div>
    <div v-if="totalSteps > 0" class="progress-bar">
      <div
        v-for="i in totalSteps"
        :key="i"
        :class="[
          'progress-segment',
          i < currentStepIndex ? 'done' : '',
          i === currentStepIndex ? 'active' : '',
        ]"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()

const LABELS: Record<string, string> = {
  planning: '正在思考',
  executing: '执行中',
  reflecting: '正在检查',
  replanning: '正在调整计划',
  answering: '生成回答',
}

const label = computed(() => {
  const p = store.phase
  if (!p) return ''
  if (p === 'executing' && store.totalSteps > 0) {
    return `执行中 — 步骤 ${store.currentStepIndex}/${store.totalSteps}`
  }
  return LABELS[p] || p
})

const message = computed(() => store.phaseMessage)
const currentStepIndex = computed(() => store.currentStepIndex)
const totalSteps = computed(() => store.totalSteps)
const phase = computed(() => store.phase)
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/ThinkingIndicator.vue
git commit -m "feat: add ThinkingIndicator component"
```

---

### Task 11: ChatInput 组件

**Files:**
- Create: `frontend-vue/src/components/ChatInput.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/ChatInput.vue -->
<template>
  <div class="flex-shrink-0 border-t border-border pt-2">
    <div class="flex gap-2">
      <input
        ref="inputRef"
        v-model="task"
        type="text"
        :disabled="disabled"
        placeholder="输入你的浏览器操作指令，例如：打开百度搜索 LangChain MCP..."
        class="flex-1 bg-transparent border-none outline-none font-serif text-[14px] text-text-body placeholder:text-text-disabled disabled:opacity-30"
        @keydown.enter="submit"
      />
      <button
        @click="submit"
        :disabled="disabled || !task.trim()"
        class="px-4 py-1 bg-accent text-white font-serif text-[13px] border-none cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
      >
        发送
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'

const props = defineProps<{ disabled: boolean }>()
const emit = defineEmits<{ submit: [task: string] }>()

const task = ref('')
const inputRef = ref<HTMLInputElement>()

function submit() {
  const trimmed = task.value.trim()
  if (!trimmed || props.disabled) return
  emit('submit', trimmed)
  task.value = ''
  nextTick(() => inputRef.value?.focus())
}
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/ChatInput.vue
git commit -m "feat: add ChatInput component"
```

---

### Task 12: ChatPanel 组件

**Files:**
- Create: `frontend-vue/src/components/ChatPanel.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/ChatPanel.vue -->
<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- Messages area -->
    <div ref="scrollRef" class="flex-1 min-h-0 overflow-y-auto px-4">
      <div
        v-if="messages.length === 0 && !processing"
        class="flex items-center justify-center h-full min-h-[200px] font-serif text-[14px] italic text-text-disabled"
      >
        输入指令，开始浏览器自动化任务
      </div>

      <ChatMessage
        v-for="(msg, i) in messages"
        :key="i"
        :role="msg.role"
        :content="msg.content"
      />

      <!-- Processing indicator -->
      <div v-if="processing" class="py-3 px-3">
        <ThinkingIndicator />
      </div>
    </div>

    <!-- Input -->
    <div class="px-4 pb-3">
      <ChatInput :disabled="processing" @submit="onSubmit" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSSE } from '@/composables/useSSE'
import ChatMessage from './ChatMessage.vue'
import ChatInput from './ChatInput.vue'
import ThinkingIndicator from './ThinkingIndicator.vue'

const store = useChatStore()
const { startTask } = useSSE()
const scrollRef = ref<HTMLDivElement>()

const messages = computed(() => store.messages)
const processing = computed(() => store.processing)

// 新消息到达时自动滚动到底部
watch(
  () => [store.messages.length, store.phaseMessage],
  async () => {
    await nextTick()
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  },
)

function onSubmit(task: string) {
  startTask(task)
}
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/ChatPanel.vue
git commit -m "feat: add ChatPanel component"
```

---

### Task 13: PlanSteps 组件

**Files:**
- Create: `frontend-vue/src/components/PlanSteps.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/PlanSteps.vue -->
<template>
  <div class="border border-card-border bg-surface p-2">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        执行计划
      </span>
      <span
        v-if="totalSteps > 0"
        class="float-right font-serif text-[18px] font-bold text-accent leading-none"
      >
        {{ currentStepIndex
        }}<span class="text-[10px] text-text-muted">/{{ totalSteps }}</span>
      </span>
    </div>
    <div v-if="steps.length === 0" class="text-text-disabled text-[12px] font-serif italic mt-2">
      等待任务...
    </div>
    <div v-else class="font-serif mt-1">
      <div
        v-for="(s, i) in steps"
        :key="i"
        :class="[
          'plan-step',
          i < currentStepIndex - 1 ? 'done' : '',
          i === currentStepIndex - 1 ? 'current' : '',
          i > currentStepIndex - 1 ? 'pending' : '',
        ]"
      >
        {{ i + 1 }}. {{ s }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const steps = computed(() => store.planSteps)
const totalSteps = computed(() => store.totalSteps)
const currentStepIndex = computed(() => store.currentStepIndex)
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/PlanSteps.vue
git commit -m "feat: add PlanSteps component"
```

---

### Task 14: TokenCounter 组件

**Files:**
- Create: `frontend-vue/src/components/TokenCounter.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/TokenCounter.vue -->
<template>
  <div class="border border-card-border bg-surface p-2">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        Token
      </span>
      <div class="text-[13px] text-text-muted mt-2 space-y-1">
        <div>输入 <b class="text-text-primary text-[14px]">{{ promptTokens.toLocaleString() }}</b></div>
        <div>输出 <b class="text-text-primary text-[14px]">{{ completionTokens.toLocaleString() }}</b></div>
        <div class="border-t border-card-border mt-1 pt-1">
          总计 <b class="text-accent text-[14px]">{{ totalTokens.toLocaleString() }}</b>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const promptTokens = computed(() => store.promptTokens)
const completionTokens = computed(() => store.completionTokens)
const totalTokens = computed(() => store.totalTokens)
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/TokenCounter.vue
git commit -m "feat: add TokenCounter component"
```

---

### Task 15: ScreenshotViewer 组件

**Files:**
- Create: `frontend-vue/src/components/ScreenshotViewer.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/ScreenshotViewer.vue -->
<template>
  <div class="border border-card-border bg-surface p-2">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        实时截图
      </span>
      <span v-if="isExecuting" class="live-dot ml-1.5"></span>
    </div>
    <div class="mt-2">
      <img
        v-if="screenshot"
        :src="'data:image/png;base64,' + screenshot"
        alt="浏览器截图"
        class="w-full max-h-[50vh] object-contain border border-card-border"
      />
      <div
        v-else
        class="border border-dashed border-card-border p-5 text-center text-text-disabled font-serif italic text-[12px]"
      >
        等待浏览器截图...
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const screenshot = computed(() => store.screenshot)
const isExecuting = computed(() => store.phase === 'executing')
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/ScreenshotViewer.vue
git commit -m "feat: add ScreenshotViewer component"
```

---

### Task 16: ReplayPanel 组件

**Files:**
- Create: `frontend-vue/src/components/ReplayPanel.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/ReplayPanel.vue -->
<template>
  <div class="border-t border-border pt-3 mt-1">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        操作回放
      </span>
    </div>

    <div v-if="sessions.length === 0" class="text-text-disabled text-[12px] font-serif italic mt-2">
      暂无历史会话
    </div>

    <template v-else>
      <div class="mt-2 flex gap-2">
        <el-select
          v-model="selected"
          size="small"
          class="flex-1"
          popper-class="replay-select-popper"
        >
          <el-option
            v-for="s in sessions"
            :key="s.id"
            :label="`${s.id} — ${s.task_summary}`"
            :value="s.id"
          />
        </el-select>
        <el-button size="small" @click="loadReplay" :loading="loadingReplay">
          查看回放
        </el-button>
      </div>

      <div v-if="replaySteps.length > 0" class="mt-3 max-h-[40vh] overflow-y-auto space-y-3">
        <div
          v-for="step in replaySteps"
          :key="step.step_index"
          class="border border-card-border bg-surface p-2"
        >
          <div class="font-serif text-[12px] text-text-muted">
            Step {{ step.step_index }}: {{ step.step }}
          </div>
          <div
            v-if="step.result"
            class="font-serif text-[12px] text-text-body mt-1"
          >
            {{ step.result }}
          </div>
          <img
            v-if="step.screenshot_path"
            :src="getScreenshotUrl(step.screenshot_path)"
            class="w-full mt-1 border border-card-border"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { fetchReplay } from '@/api/chat'
import type { ReplayStep } from '@/types'

const sessionStore = useSessionStore()
const selected = ref('')
const replaySteps = ref<ReplayStep[]>([])
const loadingReplay = ref(false)

const sessions = computed(() => sessionStore.sessions)

onMounted(() => {
  sessionStore.fetchList()
})

function getScreenshotUrl(path: string): string {
  // screenshot_path 是绝对路径或相对于 data 目录的路径
  // 本地开发时通过 vite proxy 到后端静态文件
  return `/api/screenshots/${path.replace(/\\/g, '/').split('/').pop()}`
}

async function loadReplay() {
  if (!selected.value) return
  loadingReplay.value = true
  try {
    replaySteps.value = await fetchReplay(selected.value)
  } catch {
    replaySteps.value = []
  } finally {
    loadingReplay.value = false
  }
}
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/ReplayPanel.vue
git commit -m "feat: add ReplayPanel component"
```

---

### Task 17: MonitorPanel 组件

**Files:**
- Create: `frontend-vue/src/components/MonitorPanel.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/MonitorPanel.vue -->
<template>
  <div class="h-full overflow-y-auto p-3 space-y-2">
    <div class="grid grid-cols-[3fr_1fr] gap-2">
      <PlanSteps />
      <TokenCounter />
    </div>
    <ScreenshotViewer />
    <ReplayPanel />
  </div>
</template>

<script setup lang="ts">
import PlanSteps from './PlanSteps.vue'
import TokenCounter from './TokenCounter.vue'
import ScreenshotViewer from './ScreenshotViewer.vue'
import ReplayPanel from './ReplayPanel.vue'
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/MonitorPanel.vue
git commit -m "feat: add MonitorPanel component"
```

---

### Task 18: Sidebar 组件

**Files:**
- Create: `frontend-vue/src/components/Sidebar.vue`

- [ ] **Step 1: 创建组件**

```vue
<!-- frontend-vue/src/components/Sidebar.vue -->
<template>
  <aside class="w-[220px] flex-shrink-0 bg-bg border-r border-border flex flex-col h-full">
    <!-- Brand -->
    <div class="p-4 pb-2">
      <div class="font-serif text-[20px] font-bold text-text-primary tracking-[-0.5px]">
        BrowsePilot
      </div>
      <div class="text-[12px] text-text-muted mt-0.5">浏览器自动化 AI 助手</div>
    </div>

    <div class="border-t border-border mx-3"></div>

    <!-- New Session Button -->
    <div class="px-3 py-3">
      <button
        @click="onNewSession"
        class="w-full py-2 bg-accent text-white font-serif text-[13px] border-none cursor-pointer"
      >
        新建会话
      </button>
    </div>

    <div class="border-t border-border mx-3"></div>

    <!-- Session List -->
    <div class="flex-1 min-h-0 overflow-y-auto px-3 py-2">
      <div class="text-[10px] text-text-muted tracking-[2px] uppercase mb-2 font-serif">
        历史会话
      </div>
      <div
        v-for="s in sessions"
        :key="s.id"
        :class="[
          'group flex items-center justify-between py-1.5 px-2 cursor-pointer font-serif text-[13px]',
          s.id === currentSessionId
            ? 'bg-surface border border-card-border'
            : 'hover:bg-surface',
        ]"
        @click="sessionStore.fetchList()"
      >
        <div class="flex-1 min-w-0">
          <div
            :class="[
              'truncate',
              s.id === currentSessionId ? 'text-accent' : 'text-text-body',
            ]"
          >
            {{ s.task_summary || s.id }}
          </div>
          <div class="text-[10px] text-text-disabled">{{ s.id }}</div>
        </div>
        <button
          @click.stop="onDelete(s.id)"
          class="opacity-0 group-hover:opacity-100 text-text-disabled hover:text-accent text-[14px] border-none bg-transparent cursor-pointer ml-1"
        >
          ×
        </button>
      </div>
      <div v-if="sessions.length === 0" class="text-text-disabled text-[11px] italic">
        暂无历史会话
      </div>
    </div>

    <!-- Current Session Info -->
    <div class="border-t border-border mx-3"></div>
    <div class="px-3 py-2 text-[11px] text-text-muted font-serif">
      <span v-if="currentSessionId">Session #{{ currentSessionId }}</span>
      <span v-else class="text-text-disabled italic">未连接</span>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'

const sessionStore = useSessionStore()
const chatStore = useChatStore()

const sessions = computed(() => sessionStore.sessions)
const currentSessionId = computed(() => chatStore.sessionId)

onMounted(() => {
  sessionStore.fetchList()
})

// 每次 chatStore.sessionId 变化时刷新会话列表
watch(currentSessionId, () => {
  if (currentSessionId.value) {
    sessionStore.fetchList()
  }
})

function onNewSession() {
  chatStore.reset()
  chatStore.messages = []
  chatStore.sessionId = null
}

function onDelete(id: string) {
  sessionStore.deleteSession(id)
}
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend-vue
npx vue-tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/components/Sidebar.vue
git commit -m "feat: add Sidebar component with session management"
```

---

### Task 19: App.vue 根组件

**Files:**
- Modify: `frontend-vue/src/App.vue`

- [ ] **Step 1: 替换占位 App.vue 为完整布局**

```vue
<!-- frontend-vue/src/App.vue -->
<template>
  <div class="flex h-screen bg-bg">
    <Sidebar />
    <div class="flex-1 min-w-0 grid grid-cols-[7fr_3fr]">
      <ChatPanel />
      <div class="border-l border-border">
        <MonitorPanel />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import MonitorPanel from './components/MonitorPanel.vue'
</script>
```

- [ ] **Step 2: 验证项目可构建**

```bash
cd frontend-vue
npx vue-tsc --noEmit
npm run build
```
Expected: Build 成功，输出到 `dist/`

- [ ] **Step 3: Commit**

```bash
git add frontend-vue/src/App.vue
git commit -m "feat: add App.vue root layout with three-panel design"
```

---

### Task 20: 后端截图静态文件服务

**Files:**
- Modify: `backend/app/main.py` — 添加 StaticFiles 挂载

- [ ] **Step 1: 添加截图静态文件路由**

在 `backend/app/main.py` 的 import 区域添加：
```python
from fastapi.staticfiles import StaticFiles
```

在 `app = FastAPI(...)` 之后、第一个路由之前添加：
```python
# 挂载截图目录为静态文件，支持回放加载图片
screenshots_dir = Path(settings.data_dir) / "screenshots"
screenshots_dir.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=str(screenshots_dir)), name="screenshots")
```

- [ ] **Step 2: 验证静态文件挂载**

启动后端后访问：
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/screenshots/
```
Expected: 200 或 404（如果目录为空）

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: mount screenshots directory as static files"
```

---

### Task 21: 本地集成验证

- [ ] **Step 1: 启动全部服务**

打开 3 个终端窗口：

终端 1:
```bash
cd browsepilot
python -m browser_mcp.main
```

终端 2:
```bash
cd browsepilot
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

终端 3:
```bash
cd browsepilot/frontend-vue
npm run dev
```

- [ ] **Step 2: 功能验证清单**

在 `http://localhost:5173` 验证：

1. [ ] 页面显示三栏布局：侧边栏 + 聊天区 + 监控面板
2. [ ] 输入任务后点击发送，消息出现在聊天区
3. [ ] 思考阶段显示动画圆点 + 阶段标签
4. [ ] 计划生成后右侧显示步骤列表（current/pending/done）
5. [ ] 执行阶段实时截图出现在右侧面板
6. [ ] 截图左上角有红色 live-dot 闪烁动画
7. [ ] Token 计数实时更新
8. [ ] 任务完成后最终回答出现在聊天区
9. [ ] 侧边栏显示当前 session_id
10. [ ] 历史会话出现在侧边栏列表中
11. [ ] 点击历史会话旁的 × 可删除
12. [ ] "新建会话" 按钮清空当前会话
13. [ ] 回放面板可选择历史会话并查看步骤和文本内容
14. [ ] 聊天消息自动滚动到底部

- [ ] **Step 3: 修复发现的问题**

记录并修复任何验证中发现的问题。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "fix: integration verification fixes"
```

---

### Task 22: 最终提交

- [ ] **Step 1: 确认所有更改已提交**

```bash
git status
git log --oneline -10
```

- [ ] **Step 2: 更新 README（可选）**

如果 README.md 需要更新部署说明（新增前端启动步骤）：

在 README.md 的启动说明中添加：
```markdown
### 前端启动（Vue3）

```bash
cd frontend-vue
npm install
npm run dev
```
访问 http://localhost:5173
```

- [ ] **Step 3: 最终提交**

```bash
git add README.md
git commit -m "docs: update README with Vue3 frontend startup instructions"
```

---

## 自检

1. **Spec 覆盖** — 11 个章节逐项对照：技术栈✓、目录结构✓、设计系统✓、组件架构✓、数据流✓、状态管理✓、SSE 事件✓、错误处理✓、后端 API✓、部署说明✓
2. **占位符扫描** — 无 TBD/TODO/占位符，所有步骤包含实际代码
3. **类型一致性** — `SSEEvent`、`ChatState`、`AgentPhase` 等类型在 types → stores → composables → components 链中命名一致
4. **组件接口** — 每个组件的 props/emit 定义清晰，父组件调用时有对应代码
