<!-- frontend-vue/src/components/ChatMessage.vue -->
<template>
  <div :class="['flex gap-3 py-3', role === 'user' ? 'justify-end' : 'justify-start']">
    <div
      :class="[
        'max-w-[80%] leading-relaxed text-[15px]',
        role === 'user'
          ? 'bg-surface border border-card-border px-3 py-2'
          : 'bg-transparent px-3 py-2 message-content',
      ]"
    >
      <template v-if="role === 'user'">
        {{ content }}
      </template>
      <template v-else>
        <div v-html="renderedMarkdown"></div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{
  role: 'user' | 'assistant'
  content: string
}>()

const renderedMarkdown = computed(() => {
  return marked.parse(props.content, { breaks: true }) as string
})
</script>
