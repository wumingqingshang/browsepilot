<!-- frontend-vue/src/components/ChatInput.vue -->
<template>
  <div class="flex-shrink-0 border-t border-border pt-2">
    <div class="flex gap-2">
      <input
        ref="inputRef"
        v-model="task"
        type="text"
        :disabled="disabled"
        placeholder="输入你的浏览器操作指令，例如：打开百度搜索 LangChain MCP..."
        class="flex-1 bg-transparent border-none outline-none font-serif text-[14px] text-text-body placeholder:text-text-disabled disabled:opacity-30"
        @keydown.enter="submit"
      />
      <button
        @click="submit"
        :disabled="disabled || !task.trim()"
        class="px-4 py-1 bg-accent text-white font-serif text-[13px] border-none cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
      >
        发送
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'

const props = defineProps<{ disabled: boolean }>()
const emit = defineEmits<{ submit: [task: string] }>()

const task = ref('')
const inputRef = ref<HTMLInputElement>()

function submit() {
  const trimmed = task.value.trim()
  if (!trimmed || props.disabled) return
  emit('submit', trimmed)
  task.value = ''
  nextTick(() => inputRef.value?.focus())
}
</script>
