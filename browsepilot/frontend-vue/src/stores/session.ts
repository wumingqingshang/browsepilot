// frontend-vue/src/stores/session.ts
import { defineStore } from 'pinia'
import type { SessionSummary } from '@/types'

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
  },
})
