<!-- frontend-vue/src/components/PlanSteps.vue -->
<template>
  <div class="border border-card-border bg-surface p-2">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        执行计划
      </span>
      <span
        v-if="totalSteps > 0"
        class="float-right font-serif text-[18px] font-bold text-accent leading-none"
      >
        {{ currentStepIndex
        }}<span class="text-[10px] text-text-muted">/{{ totalSteps }}</span>
      </span>
    </div>
    <div v-if="steps.length === 0" class="text-text-disabled text-[12px] font-serif italic mt-2">
      等待任务...
    </div>
    <div v-else class="font-serif mt-1">
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
