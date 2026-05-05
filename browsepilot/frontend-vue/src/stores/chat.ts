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
          // Progress update driven by thinking_status
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
