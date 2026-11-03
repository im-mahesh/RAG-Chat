import type { Chunk } from '../api.ts'
import { describeSource } from '../sources.ts'
import { useChatStore } from '../store.ts'
import styles from './CitationBadge.module.css'

interface CitationBadgeProps {
  messageId: string
  /** 1-based, as written in the answer. */
  number: number
  source: Chunk
}

export function CitationBadge({ messageId, number, source }: CitationBadgeProps) {
  const active = useChatStore(
    (state) =>
      state.activeCitation?.messageId === messageId && state.activeCitation.index === number - 1,
  )
  const openCitation = useChatStore((state) => state.openCitation)

  return (
    <button
      type="button"
      className={`${styles.badge} ${active ? styles.active : ''}`}
      onClick={() => openCitation(messageId, number - 1)}
      aria-label={`Source ${number}: ${source.filename}`}
      aria-pressed={active}
      title={describeSource(source)}
    >
      {number}
    </button>
  )
}
