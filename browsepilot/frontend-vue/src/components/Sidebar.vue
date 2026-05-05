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

// Refresh session list when sessionId changes
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
