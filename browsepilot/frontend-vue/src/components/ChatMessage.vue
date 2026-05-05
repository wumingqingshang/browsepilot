<!-- frontend-vue/src/components/ChatMessage.vue -->
<template>
  <div :class="['flex gap-3 py-3', role === 'user' ? 'justify-end' : 'justify-start']">
    <div
      :class="[
        'max-w-[80%] leading-relaxed text-[15px]',
        role === 'user'
          ? 'bg-surface border border-card-border px-3 py-2'
          : 'bg-transparent px-3 py-2',
      ]"
    >
      {{ content }}
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  role: 'user' | 'assistant'
  content: string
}>()
</script>
