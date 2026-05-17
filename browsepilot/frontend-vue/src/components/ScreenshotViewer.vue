<!-- frontend-vue/src/components/ScreenshotViewer.vue -->
<template>
  <div class="card p-[14px] flex flex-col" style="max-height:35vh">
    <div class="shrink-0">
      <span class="font-sans text-[10px] text-text-muted-deep tracking-[1.5px] uppercase font-semibold">
        实时截图
      </span>
      <span v-if="isExecuting" class="live-dot ml-1.5"></span>
    </div>
    <div class="mt-2 overflow-y-auto flex-1 min-h-0">
      <img
        v-if="screenshot"
        :src="'data:image/png;base64,' + screenshot"
        alt="浏览器截图"
        class="w-full object-contain border border-card-border cursor-zoom-in hover:opacity-90 transition-opacity"
        @click="showLightbox = true"
      />
      <div
        v-else
        class="border border-dashed border-card-border p-5 text-center text-text-disabled font-serif italic text-[12px]"
      >
        等待浏览器截图...
      </div>
    </div>

    <!-- Lightbox with zoom/pan -->
    <Teleport to="body">
      <div
        v-if="showLightbox"
        class="fixed inset-0 z-50 bg-black/90 flex items-center justify-center overflow-hidden"
        @wheel.prevent="onWheel"
        @mousedown="onPanStart"
        @mousemove="onPanMove"
        @mouseup="onPanEnd"
        @mouseleave="onPanEnd"
        @dblclick="resetZoom"
      >
        <img
          :src="'data:image/png;base64,' + screenshot"
          alt="浏览器截图（放大）"
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
          @click.stop="showLightbox = false"
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

const store = useChatStore()
const screenshot = computed(() => store.screenshot)
const isExecuting = computed(() => store.phase === 'executing')
const showLightbox = ref(false)

// Zoom/pan state
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const lastMouseX = ref(0)
const lastMouseY = ref(0)

watch(showLightbox, (val) => {
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

  // Zoom toward cursor position
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
</script>
