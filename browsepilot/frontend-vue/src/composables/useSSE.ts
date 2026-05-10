// frontend-vue/src/composables/useSSE.ts
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { streamChat } from '@/api/chat'

export function useSSE() {
  const store = useChatStore()
  const sessionStore = useSessionStore()
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
      // Refresh session list after task completes
      sessionStore.fetchList()
    }
  }

  function cancel() {
    controller?.abort()
  }

  return { startTask, cancel, errorMessage }
}
