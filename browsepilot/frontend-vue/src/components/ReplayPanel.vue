<!-- frontend-vue/src/components/ReplayPanel.vue -->
<template>
  <div class="border-t border-border pt-3 mt-1">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        操作回放
      </span>
    </div>

    <div v-if="!currentSessionId" class="text-text-disabled text-[12px] font-serif italic mt-2">
      点击左侧会话查看执行回放
    </div>

    <div v-else-if="loadingReplay" class="text-text-muted text-[12px] font-serif mt-2">
      加载中...
    </div>

    <div
      v-else-if="replaySteps.length > 0"
      class="mt-3 max-h-[40vh] overflow-y-auto space-y-3"
    >
      <div
        v-for="step in replaySteps"
        :key="step.step_index"
        class="border border-card-border bg-surface p-2"
      >
        <div class="font-serif text-[12px] text-text-muted">
          Step {{ step.step_index }}: {{ step.step }}
        </div>
        <div
          v-if="step.result && Object.keys(step.result).length > 0"
          class="font-serif text-[12px] text-text-body mt-1"
        >
          {{ formatResult(step.result) }}
        </div>
        <img
          v-if="step.screenshot_path"
          :src="getScreenshotUrl(step.screenshot_path)"
          class="w-full mt-1 border border-card-border"
        />
      </div>
    </div>

    <div
      v-else
      class="text-text-muted text-[12px] font-serif mt-2"
    >
      该会话无回放数据
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { fetchReplay } from '@/api/chat'
import type { ReplayStep } from '@/types'

const chatStore = useChatStore()
const replaySteps = ref<ReplayStep[]>([])
const loadingReplay = ref(false)

const currentSessionId = computed(() => chatStore.sessionId)

watch(currentSessionId, async (id) => {
  if (!id) {
    replaySteps.value = []
    return
  }
  loadingReplay.value = true
  try {
    replaySteps.value = await fetchReplay(id)
  } catch {
    replaySteps.value = []
  } finally {
    loadingReplay.value = false
  }
}, { immediate: true })

function getScreenshotUrl(path: string): string {
  if (!path) return ''
  const filename = path.replace(/\\/g, '/').split('/').pop() || ''
  return `/api/screenshots/${filename}`
}

function formatResult(result: Record<string, any>): string {
  if (typeof result === 'string') return result
  try {
    return JSON.stringify(result)
  } catch {
    return String(result)
  }
}
</script>
