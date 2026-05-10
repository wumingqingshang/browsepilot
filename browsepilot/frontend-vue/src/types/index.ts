// frontend-vue/src/types/index.ts

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  _streaming?: boolean
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
