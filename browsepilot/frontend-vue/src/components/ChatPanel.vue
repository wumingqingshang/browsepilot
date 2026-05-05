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

    <!-- Input — hidden when viewing history; shown otherwise -->
    <div v-if="!isViewingHistory" class="px-4 pb-3">
      <ChatInput :disabled="processing" @submit="onSubmit" />
    </div>
    <div v-else class="px-4 pb-3 text-center">
      <span class="text-[11px] text-text-disabled font-serif italic">
        正在查看历史会话 — 点击「新建会话」返回
      </span>
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
const isViewingHistory = computed(() => !store.processing && store.sessionId && store.messages.length > 0 && !store.phase)

// Auto-scroll to bottom when new messages arrive
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
