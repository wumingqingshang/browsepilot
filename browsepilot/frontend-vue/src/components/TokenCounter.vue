<!-- frontend-vue/src/components/TokenCounter.vue -->
<template>
  <div class="card p-[14px]">
    <span class="font-sans text-[10px] text-text-muted-deep tracking-[1.5px] uppercase font-semibold">
      Token
    </span>
    <div class="text-[12px] text-text-muted mt-[10px] space-y-[3px]">
      <div>输入 <b class="font-sans text-[13px] text-text-primary">{{ promptTokens.toLocaleString() }}</b></div>
      <div>输出 <b class="font-sans text-[13px] text-text-primary">{{ completionTokens.toLocaleString() }}</b></div>
      <div class="border-t border-border mt-[6px] pt-[6px]">
        总计 <b class="font-sans text-[14px] text-accent">{{ totalTokens.toLocaleString() }}</b><span v-if="tokenEstimated" class="text-[10px] text-text-muted ml-1">(估算)</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const promptTokens = computed(() => store.promptTokens)
const completionTokens = computed(() => store.completionTokens)
const totalTokens = computed(() => store.totalTokens)
const tokenEstimated = computed(() => store.tokenEstimated)
</script>
