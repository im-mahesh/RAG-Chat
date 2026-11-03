import { useEffect, useRef } from 'react'
import { useChatStore } from '../store.ts'
import { MessageBubble } from './MessageBubble.tsx'
import styles from './MessageList.module.css'

const STICK_TO_BOTTOM_PX = 80

export function MessageList({ streaming }: { streaming: boolean }) {
  const messages = useChatStore((state) => state.messages)
  const listRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  useEffect(() => {
    const list = listRef.current
    if (list && stickToBottom.current) list.scrollTop = list.scrollHeight
  }, [messages])

  function handleScroll() {
    const list = listRef.current
    if (!list) return
    const distance = list.scrollHeight - list.scrollTop - list.clientHeight
    stickToBottom.current = distance < STICK_TO_BOTTOM_PX
  }

  if (messages.length === 0) {
    return (
      <div className={styles.empty}>
        <p>Upload a document, then ask a question about it.</p>
      </div>
    )
  }

  return (
    <div
      ref={listRef}
      className={styles.list}
      onScroll={handleScroll}
      role="log"
      aria-live="polite"
      aria-busy={streaming}
      aria-label="Conversation"
    >
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
    </div>
  )
}
