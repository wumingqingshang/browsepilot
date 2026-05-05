<template>
  <div class="border-t border-border pt-3 mt-1">
    <div class="font-serif">
      <span class="text-[15px] text-text-muted tracking-[2px] uppercase font-bold">
        操作回放
      </span>
    </div>

    <div v-if="sessions.length === 0" class="text-text-disabled text-[12px] font-serif italic mt-2">
      暂无历史会话
    </div>

    <template v-else>
      <div class="mt-2 flex gap-2">
        <el-select
          v-model="selected"
          size="small"
          class="flex-1"
          popper-class="replay-select-popper"
        >
          <el-option
            v-for="s in sessions"
            :key="s.id"
            :label="`${s.id} — ${s.task_summary}`"
            :value="s.id"
          />
        </el-select>
        <el-button size="small" @click="loadReplay" :loading="loadingReplay">
          查看回放
        </el-button>
      </div>

      <div v-if="replaySteps.length > 0" class="mt-3 max-h-[40vh] overflow-y-auto space-y-3">
        <div
          v-for="step in replaySteps"
          :key="step.step_index"
          class="border border-card-border bg-surface p-2"
        >
          <div class="font-serif text-[12px] text-text-muted">
            Step {{ step.step_index }}: {{ step.step }}
          </div>
          <div
            v-if="step.result && Object.keys(step.result).length > 0"
            class="font-serif text-[12px] text-text-body mt-1"
          >
            {{ typeof step.result === 'string' ? step.result : JSON.stringify(step.result) }}
          </div>
          <img
            v-if="step.screenshot_path"
            :src="getScreenshotUrl(step.screenshot_path)"
            class="w-full mt-1 border border-card-border"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { fetchReplay } from '@/api/chat'
import type { ReplayStep } from '@/types'

const sessionStore = useSessionStore()
const selected = ref('')
const replaySteps = ref<ReplayStep[]>([])
const loadingReplay = ref(false)

const sessions = computed(() => sessionStore.sessions)

onMounted(() => {
  sessionStore.fetchList()
})

function getScreenshotUrl(path: string): string {
  if (!path) return ''
  const filename = path.replace(/\\/g, '/').split('/').pop() || ''
  return `/api/screenshots/${filename}`
}

async function loadReplay() {
  if (!selected.value) return
  loadingReplay.value = true
  try {
    replaySteps.value = await fetchReplay(selected.value)
  } catch {
    replaySteps.value = []
  } finally {
    loadingReplay.value = false
  }
}
</script>
