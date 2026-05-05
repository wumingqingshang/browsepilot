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
        class="w-full max-h-[50vh] object-contain border border-card-border"
      />
      <div
        v-else
        class="border border-dashed border-card-border p-5 text-center text-text-disabled font-serif italic text-[12px]"
      >
        等待浏览器截图...
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const screenshot = computed(() => store.screenshot)
const isExecuting = computed(() => store.phase === 'executing')
</script>
