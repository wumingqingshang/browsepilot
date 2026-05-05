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
