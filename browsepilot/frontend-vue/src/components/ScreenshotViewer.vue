<!-- frontend-vue/src/components/ScreenshotViewer.vue -->
<template>
  <div class="border border-card-border bg-surface p-2">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        实时截图
      </span>
      <span v-if="isExecuting" class="live-dot ml-1.5"></span>
    </div>
    <div class="mt-2">
      <img
        v-if="screenshot"
        :src="'data:image/png;base64,' + screenshot"
        alt="浏览器截图"
        class="w-full max-h-[50vh] object-contain border border-card-border cursor-zoom-in hover:opacity-90 transition-opacity"
        @click="showLightbox = true"
      />
      <div
        v-else
        class="border border-dashed border-card-border p-5 text-center text-text-disabled font-serif italic text-[12px]"
      >
        等待浏览器截图...
      </div>
    </div>

    <!-- Lightbox -->
    <Teleport to="body">
      <div
        v-if="showLightbox"
        class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-8"
        @click="showLightbox = false"
      >
        <img
          :src="'data:image/png;base64,' + screenshot"
          alt="浏览器截图（放大）"
          class="max-w-full max-h-full object-contain"
        />
        <button
          class="absolute top-4 right-4 text-white text-[24px] bg-transparent border-none cursor-pointer opacity-60 hover:opacity-100"
          @click="showLightbox = false"
        >
          ×
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const screenshot = computed(() => store.screenshot)
const isExecuting = computed(() => store.phase === 'executing')
const showLightbox = ref(false)
</script>
