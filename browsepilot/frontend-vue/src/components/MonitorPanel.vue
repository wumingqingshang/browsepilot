<!-- frontend-vue/src/components/MonitorPanel.vue -->
<template>
  <div class="h-full overflow-y-auto p-3 space-y-2 min-w-0">
    <div class="grid grid-cols-[3fr_1fr] gap-2">
      <PlanSteps />
      <TokenCounter />
    </div>
    <ScreenshotViewer />
    <ReplayPanel />
  </div>
</template>

<script setup lang="ts">
import PlanSteps from './PlanSteps.vue'
import TokenCounter from './TokenCounter.vue'
import ScreenshotViewer from './ScreenshotViewer.vue'
import ReplayPanel from './ReplayPanel.vue'
</script>
