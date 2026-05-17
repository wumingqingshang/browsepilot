<!-- frontend-vue/src/components/ReplayPanel.vue -->
<template>
  <div class="border-t border-border pt-3 mt-1 min-w-0 flex flex-col overflow-hidden h-full">
    <span class="font-sans text-[10px] text-text-muted-deep tracking-[1.5px] uppercase font-semibold">
      操作回放
    </span>

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
        class="card p-2 min-w-0"
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

    <!-- Lightbox with zoom/pan -->
    <Teleport to="body">
      <div
        v-if="lightboxSrc"
        class="fixed inset-0 z-50 bg-black/90 flex items-center justify-center overflow-hidden"
        @wheel.prevent="onWheel"
        @mousedown="onPanStart"
        @mousemove="onPanMove"
        @mouseup="onPanEnd"
        @mouseleave="onPanEnd"
        @dblclick="resetZoom"
      >
        <img
          :src="lightboxSrc"
          alt="回放截图（放大）"
          :style="{
            transform: `translate(${panX}px, ${panY}px) scale(${scale})`,
            cursor: scale > 1 ? (isPanning ? 'grabbing' : 'grab') : 'zoom-in',
            transition: isPanning ? 'none' : 'transform 0.15s ease-out',
          }"
          class="max-w-[90vw] max-h-[90vh] object-contain select-none"
          @click.stop
        />
        <button
          class="absolute top-4 right-4 text-white text-[28px] bg-black/30 hover:bg-black/50 rounded-full w-10 h-10 flex items-center justify-center border-none cursor-pointer z-10"
          @click.stop="lightboxSrc = ''"
        >
          ×
        </button>
        <div class="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/60 text-[12px] font-serif bg-black/30 px-3 py-1 rounded">
          {{ Math.round(scale * 100) }}% — 滚轮缩放 | 拖拽平移 | 双击还原
        </div>
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

// Zoom/pan state
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const lastMouseX = ref(0)
const lastMouseY = ref(0)

watch(lightboxSrc, (val) => {
  if (!val) {
    scale.value = 1
    panX.value = 0
    panY.value = 0
  }
})

const MIN_SCALE = 0.5
const MAX_SCALE = 5
const ZOOM_STEP = 0.25

function onWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP
  const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value + delta))
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const cx = e.clientX - rect.left - rect.width / 2
  const cy = e.clientY - rect.top - rect.height / 2
  const ratio = newScale / scale.value
  panX.value = panX.value * ratio + cx * (1 - ratio)
  panY.value = panY.value * ratio + cy * (1 - ratio)
  scale.value = newScale
}

function onPanStart(e: MouseEvent) {
  if (scale.value <= 1) return
  isPanning.value = true
  lastMouseX.value = e.clientX
  lastMouseY.value = e.clientY
}

function onPanMove(e: MouseEvent) {
  if (!isPanning.value) return
  panX.value += e.clientX - lastMouseX.value
  panY.value += e.clientY - lastMouseY.value
  lastMouseX.value = e.clientX
  lastMouseY.value = e.clientY
}

function onPanEnd() {
  isPanning.value = false
}

function resetZoom() {
  scale.value = 1
  panX.value = 0
  panY.value = 0
}

const currentSessionId = computed(() => chatStore.sessionId)

watch(currentSessionId, async (id) => {
  if (!id) {
    replaySteps.value = []
    return
  }
  await loadReplay(id)
}, { immediate: true })

// Re-fetch replay when task completes (processing: true -> false)
watch(() => chatStore.processing, (newVal, oldVal) => {
  if (oldVal && !newVal && chatStore.sessionId) {
    loadReplay(chatStore.sessionId)
  }
})

async function loadReplay(id: string) {
  loadingReplay.value = true
  try {
    replaySteps.value = await fetchReplay(id)
  } catch {
    replaySteps.value = []
  } finally {
    loadingReplay.value = false
  }
}

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
