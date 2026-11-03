import { useAsk } from '../hooks/useAsk.ts'
import { useDocuments } from '../hooks/useDocuments.ts'
import { useChatStore } from '../store.ts'
import { ChatInput } from './ChatInput.tsx'
import styles from './ChatPane.module.css'
import { HealthBadge } from './HealthBadge.tsx'
import { MessageList } from './MessageList.tsx'

export function ChatPane() {
  const { ask, stop, isStreaming } = useAsk()
  const { data: documents } = useDocuments()
  const hasMessages = useChatStore((state) => state.messages.length > 0)
  const clearMessages = useChatStore((state) => state.clearMessages)
  const setSidebarOpen = useChatStore((state) => state.setSidebarOpen)
  const noDocuments = documents !== undefined && documents.length === 0

  return (
    <main className={styles.pane}>
      <header className={styles.header}>
        <button type="button" className={styles.menu} onClick={() => setSidebarOpen(true)}>
          Documents
        </button>
        <h1 className={styles.title}>DocChat</h1>
        <div className={styles.actions}>
          {hasMessages && (
            <button
              type="button"
              className={styles.clear}
              onClick={clearMessages}
              disabled={isStreaming}
            >
              Clear chat
            </button>
          )}
          <HealthBadge />
        </div>
      </header>
      <MessageList streaming={isStreaming} />
      <ChatInput
        disabled={isStreaming || noDocuments}
        streaming={isStreaming}
        placeholder={noDocuments ? 'Upload a document to start chatting' : 'Ask about your documents…'}
        onSend={ask}
        onStop={stop}
      />
    </main>
  )
}
