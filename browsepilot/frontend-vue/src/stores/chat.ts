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
          // Don't set currentStepIndex here — thinking_status step_index is
          // global across replans. step_start handles plan-relative increment.
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
          // Increment locally — step_index is global across replans,
          // but currentStepIndex should track position within current plan
          this.currentStepIndex += 1
          break

        case 'screenshot':
          if (d.base64) this.screenshot = d.base64
          break

        case 'step_end':
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

        case 'answer_chunk':
          // Streaming answer — append to last assistant message
          const lastMsg = this.messages[this.messages.length - 1]
          if (lastMsg && lastMsg.role === 'assistant' && lastMsg._streaming) {
            lastMsg.content += d.content || ''
          } else {
            const msg: ChatMessage = { role: 'assistant', content: d.content || '', _streaming: true }
            this.messages.push(msg)
          }
          break

        case 'final_answer':
          // Finalize streaming — mark message as complete
          const last = this.messages[this.messages.length - 1]
          if (last && last.role === 'assistant' && (last as any)._streaming) {
            (last as any)._streaming = false
            // Update content if final_answer provides the full text
            if (d.content && d.content !== last.content) {
              last.content = d.content
            }
          } else if (d.content) {
            this.messages.push({ role: 'assistant', content: d.content || '' })
          }
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

    viewHistory(sessionId: string, task: string, answer: string) {
      this.sessionId = sessionId
      this.messages = [
        { role: 'user', content: task },
        { role: 'assistant', content: answer },
      ]
      this.processing = false
      this.phase = null
      this.screenshot = null
      this.planSteps = []
      this.currentStepIndex = 0
      this.totalSteps = 0
    },
  },
})
