<!-- frontend-vue/src/components/TokenCounter.vue -->
<template>
  <div class="border border-card-border bg-surface p-2">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        Token
      </span>
      <div class="text-[13px] text-text-muted mt-2 space-y-1">
        <div>输入 <b class="text-text-primary text-[14px]">{{ promptTokens.toLocaleString() }}</b></div>
        <div>输出 <b class="text-text-primary text-[14px]">{{ completionTokens.toLocaleString() }}</b></div>
        <div class="border-t border-card-border mt-1 pt-1">
          总计 <b class="text-accent text-[14px]">{{ totalTokens.toLocaleString() }}</b><span v-if="tokenEstimated" class="text-[10px] text-text-muted ml-1">(估算)</span>
        </div>
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
