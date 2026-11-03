import type { ChatMessage } from '../store.ts'
import { MarkdownContent } from './MarkdownContent.tsx'
import styles from './MessageBubble.module.css'
import { Sources } from './Sources.tsx'

function WaitingDots() {
  return (
    <span className={styles.dots} role="status" aria-label="Waiting for an answer">
      <span />
      <span />
      <span />
    </span>
  )
}

function AssistantBody({ message }: { message: ChatMessage }) {
  if (message.streaming && message.content === '') return <WaitingDots />
  if (message.content === '' && message.stopped) return <p className={styles.note}>Stopped.</p>
  return (
    <>
      <MarkdownContent
        messageId={message.id}
        content={message.content}
        sources={message.sources ?? []}
        streaming={message.streaming}
      />
      {message.stopped && <p className={styles.note}>Stopped.</p>}
    </>
  )
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isAssistant = message.role === 'assistant'
  return (
    <div className={`${styles.message} ${styles[message.role]}`}>
      <div className={styles.bubble}>
        {isAssistant ? <AssistantBody message={message} /> : <p className={styles.text}>{message.content}</p>}
        {isAssistant && message.sources && <Sources messageId={message.id} sources={message.sources} />}
      </div>
    </div>
  )
}
