import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export interface SourceData {
  metadata: {
    chunk_id: string
    filename: string
    page: number
    chunk_index: number
    score: number
  }
  elements: { type: string; content: string; image_url: string | null }[]
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  total_ms?: number
  sources?: SourceData[]
  timestamp: string
}

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: Message[]
  dataset_ids: string[]
  doc_ids: string[]
}

const STORAGE_KEY = 'rag_query_sessions'

function loadSessions(): { sessions: Session[]; active_session_id: string | null } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return { sessions: [], active_session_id: null }
}

function saveSessions(data: { sessions: Session[]; active_session_id: string | null }) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
}

export const useQuerySessionStore = defineStore('querySession', () => {
  const initial = loadSessions()
  const sessions = ref<Session[]>(initial.sessions)
  const activeSessionId = ref<string | null>(initial.active_session_id)

  watch([sessions, activeSessionId], () => {
    saveSessions({ sessions: sessions.value, active_session_id: activeSessionId.value })
  }, { deep: true })

  function createSession() {
    const id = `sess_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
    const now = new Date().toISOString()
    const session: Session = { id, title: '新对话', created_at: now, updated_at: now, messages: [], dataset_ids: [], doc_ids: [] }
    sessions.value.unshift(session)
    activeSessionId.value = id
    return session
  }

  function getActiveSession(): Session | undefined {
    return sessions.value.find((s) => s.id === activeSessionId.value)
  }

  function switchSession(id: string) {
    activeSessionId.value = id
  }

  function deleteSession(id: string) {
    sessions.value = sessions.value.filter((s) => s.id !== id)
    if (activeSessionId.value === id) {
      activeSessionId.value = sessions.value.length > 0 ? sessions.value[0].id : null
    }
  }

  function renameSession(id: string, title: string) {
    const s = sessions.value.find((s) => s.id === id)
    if (s) s.title = title
  }

  function addMessage(sessionId: string, msg: Message) {
    const s = sessions.value.find((s) => s.id === sessionId)
    if (!s) return
    s.messages.push(msg)
    s.updated_at = new Date().toISOString()
    if (msg.role === 'user' && s.title === '新对话') {
      s.title = msg.content.slice(0, 30)
    }
  }

  return { sessions, activeSessionId, createSession, getActiveSession, switchSession, deleteSession, renameSession, addMessage }
})
