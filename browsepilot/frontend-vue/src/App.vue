<template>
  <div class="flex h-screen bg-bg">
    <Sidebar />
    <div class="flex-1 min-w-0 min-h-0 grid grid-cols-[7fr_3fr] grid-rows-1">
      <ChatPanel />
      <div class="border-l border-border">
        <MonitorPanel />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import MonitorPanel from './components/MonitorPanel.vue'
import { useChatStore } from './stores/chat'
import { useSessionStore } from './stores/session'

const chatStore = useChatStore()
const sessionStore = useSessionStore()

onMounted(async () => {
  await sessionStore.fetchList()

  // Priority 1: URL hash (#session=abc123)
  const hash = window.location.hash
  const hashMatch = hash.match(/session=(\S+)/)
  if (hashMatch) {
    const sessionId = hashMatch[1]
    await sessionStore.loadSessionHistory(sessionId)
    return
  }

  // Priority 2: localStorage fallback
  const stored = localStorage.getItem('browsepilot_last_session')
  if (stored) {
    await sessionStore.loadSessionHistory(stored)
  }
})

// Persist active session to URL hash and localStorage on changes
watch(
  () => chatStore.sessionId,
  (id: string | null) => {
    if (id) {
      localStorage.setItem('browsepilot_last_session', id)
      window.location.hash = `session=${id}`
    }
  },
)
</script>
