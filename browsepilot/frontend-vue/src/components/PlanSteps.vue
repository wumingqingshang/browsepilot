<!-- frontend-vue/src/components/PlanSteps.vue -->
<template>
  <div class="card p-[14px]">
    <div class="flex justify-between items-baseline">
      <span class="font-sans text-[10px] text-text-muted-deep tracking-[1.5px] uppercase font-semibold">
        执行计划
      </span>
      <span
        v-if="totalSteps > 0"
        class="font-serif text-[20px] font-bold text-accent leading-none"
      >
        {{ Math.min(currentStepIndex, totalSteps)
        }}<span class="font-sans text-[10px] text-text-muted font-normal"> / {{ totalSteps }}</span>
      </span>
    </div>
    <div v-if="steps.length === 0" class="text-text-disabled text-[12px] italic mt-2 font-serif">
      等待任务...
    </div>
    <div v-else class="mt-1">
      <div
        v-for="(s, i) in steps"
        :key="i"
        :class="[
          'plan-step',
          i < currentStepIndex - 1 ? 'done' : '',
          i === currentStepIndex - 1 ? 'current' : '',
          i > currentStepIndex - 1 ? 'pending' : '',
        ]"
      >
        {{ i + 1 }}. {{ s }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const steps = computed(() => store.planSteps)
const totalSteps = computed(() => store.totalSteps)
const currentStepIndex = computed(() => store.currentStepIndex)
</script>
