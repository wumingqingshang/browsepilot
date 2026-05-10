<!-- frontend-vue/src/components/ReplayPanel.vue -->
<template>
  <div class="border-t border-border pt-3 mt-1 min-w-0 flex flex-col overflow-hidden h-full">
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
      class="mt-3 space-y-3 overflow-y-auto flex-1 min-h-0"
    >
      <div
        v-for="step in replaySteps"
        :key="step.step_index"
        class="border border-card-border bg-surface p-2 min-w-0"
      >
        <div class="font-serif text-[12px] text-text-muted">
          Step {{ step.step_index }}: {{ step.step }}
        </div>
        <div
          v-if="statusText(step.result)"
          class="font-serif text-[11px] text-text-muted mt-0.5"
        >
          {{ statusText(step.result) }}
        </div>
        <img
          v-if="step.screenshot_path"
          :src="getScreenshotUrl(step.screenshot_path)"
          class="max-w-full max-h-[30vh] object-contain mt-1 border border-card-border cursor-zoom-in hover:opacity-90 transition-opacity"
          @error="onImgError($event)"
          @click="lightboxSrc = getScreenshotUrl(step.screenshot_path)"
        />
      </div>
    </div>

    <div
      v-else
      class="text-text-muted text-[12px] font-serif mt-2"
    >
      该会话无回放数据
    </div>

    <!-- Lightbox -->
    <Teleport to="body">
      <div
        v-if="lightboxSrc"
        class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-8"
        @click="lightboxSrc = ''"
      >
        <img
          :src="lightboxSrc"
          alt="回放截图（放大）"
          class="max-w-full max-h-full object-contain"
        />
        <button
          class="absolute top-4 right-4 text-white text-[24px] bg-transparent border-none cursor-pointer opacity-60 hover:opacity-100"
          @click="lightboxSrc = ''"
        >
          ×
        </button>
      </div>
    </Teleport>
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
const lightboxSrc = ref('')

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
  // Path is like "data/screenshots/{session_id}/step_X.png"
  // Extract everything after "screenshots/" to preserve session subdirectory
  const normalized = path.replace(/\\/g, '/')
  const idx = normalized.indexOf('screenshots/')
  if (idx !== -1) {
    return '/api/' + normalized.substring(idx)
  }
  // Fallback: old flat format
  const filename = normalized.split('/').pop() || ''
  return `/api/screenshots/${filename}`
}

function statusText(result: Record<string, any>): string {
  if (!result || Object.keys(result).length === 0) return ''
  const status = result.status
  const hasStructure = result.structure && Object.keys(result.structure).length > 0
  const parts: string[] = []
  if (status) parts.push(`状态: ${status}`)
  if (hasStructure) parts.push('页面结构数据已获取')
  return parts.join(' | ')
}

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}
</script>
