<!-- frontend-vue/src/components/MonitorPanel.vue -->
<template>
  <div class="h-full flex flex-col overflow-hidden p-3 space-y-2 min-w-0">
    <div class="grid grid-cols-[3fr_1fr] gap-2 shrink-0">
      <PlanSteps />
      <TokenCounter />
    </div>
    <ScreenshotViewer class="shrink-0" />
    <ReplayPanel class="flex-1 min-h-0" />
  </div>
</template>

<script setup lang="ts">
import PlanSteps from './PlanSteps.vue'
import TokenCounter from './TokenCounter.vue'
import ScreenshotViewer from './ScreenshotViewer.vue'
import ReplayPanel from './ReplayPanel.vue'
</script>
