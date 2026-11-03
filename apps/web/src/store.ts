import { create } from 'zustand'
import type { Chunk } from './api.ts'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'error'
  content: string
  sources?: Chunk[]
  /** True while tokens are still arriving for this assistant message. */
  streaming?: boolean
  /** True if the user stopped the answer before it finished. */
  stopped?: boolean
}

/** The source (0-based index into the message's sources) shown in the side panel. */
export interface ActiveCitation {
  messageId: string
  index: number
}

interface ChatState {
  messages: ChatMessage[]
  selectedDocumentIds: string[]
  sidebarOpen: boolean
  activeCitation: ActiveCitation | null
  openCitation: (messageId: string, index: number) => void
  closeCitation: () => void
  addMessage: (message: Omit<ChatMessage, 'id'>) => string
  updateMessage: (id: string, patch: Partial<Omit<ChatMessage, 'id'>>) => void
  appendToMessage: (id: string, text: string) => void
  removeMessage: (id: string) => void
  clearMessages: () => void
  toggleDocument: (id: string) => void
  clearSelection: () => void
  pruneSelection: (existingIds: string[]) => void
  setSidebarOpen: (open: boolean) => void
}

function mapMessage(
  messages: ChatMessage[],
  id: string,
  change: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return messages.map((message) => (message.id === id ? change(message) : message))
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  selectedDocumentIds: [],
  sidebarOpen: false,
  activeCitation: null,
  openCitation: (messageId, index) => set({ activeCitation: { messageId, index } }),
  closeCitation: () => set({ activeCitation: null }),
  addMessage: (message) => {
    const id = crypto.randomUUID()
    set((state) => ({ messages: [...state.messages, { ...message, id }] }))
    return id
  },
  updateMessage: (id, patch) =>
    set((state) => ({ messages: mapMessage(state.messages, id, (m) => ({ ...m, ...patch })) })),
  appendToMessage: (id, text) =>
    set((state) => ({
      messages: mapMessage(state.messages, id, (m) => ({ ...m, content: m.content + text })),
    })),
  removeMessage: (id) =>
    set((state) => ({ messages: state.messages.filter((message) => message.id !== id) })),
  clearMessages: () => set({ messages: [], activeCitation: null }),
  toggleDocument: (id) =>
    set((state) => ({
      selectedDocumentIds: state.selectedDocumentIds.includes(id)
        ? state.selectedDocumentIds.filter((x) => x !== id)
        : [...state.selectedDocumentIds, id],
    })),
  clearSelection: () => set({ selectedDocumentIds: [] }),
  pruneSelection: (existingIds) =>
    set((state) => {
      const kept = state.selectedDocumentIds.filter((id) => existingIds.includes(id))
      return kept.length === state.selectedDocumentIds.length
        ? state
        : { selectedDocumentIds: kept }
    }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
}))
