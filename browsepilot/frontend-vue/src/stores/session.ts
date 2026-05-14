// frontend-vue/src/stores/session.ts
import { defineStore } from 'pinia'
import type { SessionSummary } from '@/types'
import { useChatStore } from './chat'

const API_BASE = '/api'

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as SessionSummary[],
    loading: false,
  }),

  actions: {
    async fetchList() {
      this.loading = true
      try {
        const resp = await fetch(`${API_BASE}/sessions`)
        if (resp.ok) {
          this.sessions = await resp.json()
        }
      } catch {
        // Backend unavailable — silently ignore
      } finally {
        this.loading = false
      }
    },

    async deleteSession(id: string) {
      try {
        const resp = await fetch(`${API_BASE}/sessions/${id}`, { method: 'DELETE' })
        if (resp.ok) {
          this.sessions = this.sessions.filter(s => s.id !== id)
        }
      } catch {
        // Silently ignore
      }
    },

    async renameSession(id: string, name: string) {
      try {
        const resp = await fetch(`${API_BASE}/sessions/${id}/rename`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        })
        if (resp.ok) {
          const s = this.sessions.find(s => s.id === id)
          if (s) s.custom_name = name
        }
      } catch {
        // Silently ignore
      }
    },

    async togglePin(id: string, pinned: boolean) {
      try {
        const resp = await fetch(`${API_BASE}/sessions/${id}/pin`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pinned }),
        })
        if (resp.ok) {
          const s = this.sessions.find(s => s.id === id)
          if (s) s.pinned = pinned
          // Re-sort: pinned first
          this.sessions.sort((a, b) => {
            if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
            return 0
          })
        }
      } catch {
        // Silently ignore
      }
    },

    async loadSessionHistory(sessionId: string) {
      try {
        const resp = await fetch(`${API_BASE}/history/${sessionId}`)
        if (!resp.ok) return
        const data = await resp.json()
        const chatStore = useChatStore()
        chatStore.viewHistory(
          sessionId,
          data.task || '',
          data.final_answer || '',
          data.token_usage || undefined,
        )
      } catch {
        // Silently ignore
      }
    },
  },
})
