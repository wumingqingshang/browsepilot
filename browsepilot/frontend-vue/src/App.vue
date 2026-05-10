<template>
  <div class="flex h-screen bg-bg">
    <Sidebar />
    <div class="flex-1 min-w-0 min-h-0 grid grid-cols-[7fr_3fr] grid-rows-1">
      <ChatPanel />
      <div class="border-l border-border">
        <MonitorPanel />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import MonitorPanel from './components/MonitorPanel.vue'
</script>
