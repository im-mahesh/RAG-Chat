import { useEffect, useRef } from 'react'
import { useChatStore } from '../store.ts'
import { SourceCard } from './SourceCard.tsx'
import styles from './SourcePanel.module.css'

function useEscapeToClose(open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return
    const trigger = document.activeElement
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      if (trigger instanceof HTMLElement) trigger.focus()
    }
  }, [open, close])
}

/**
 * Shows the sources of the answer a badge belongs to, with the cited one
 * expanded and highlighted. An inline column on wide screens, an overlay
 * (modal) on narrow ones.
 */
export function SourcePanel() {
  const active = useChatStore((state) => state.activeCitation)
  const sources = useChatStore(
    (state) => state.messages.find((m) => m.id === state.activeCitation?.messageId)?.sources,
  )
  const openCitation = useChatStore((state) => state.openCitation)
  const closeCitation = useChatStore((state) => state.closeCitation)
  const selectedRef = useRef<HTMLDivElement>(null)
  const open = active !== null && sources !== undefined

  useEscapeToClose(open, closeCitation)
  useEffect(() => {
    selectedRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [active?.messageId, active?.index])

  if (!open) return null
  return (
    <>
      <button
        type="button"
        className={styles.backdrop}
        onClick={closeCitation}
        aria-label="Close source"
        tabIndex={-1}
      />
      <aside className={styles.panel} aria-label="Source details">
        <div className={styles.header}>
          <h2 className={styles.title}>
            Source {active.index + 1} of {sources.length}
          </h2>
          <button type="button" className={styles.close} onClick={closeCitation} aria-label="Close source">
            ×
          </button>
        </div>
        <div className={styles.cards}>
          {sources.map((source, index) => {
            const selected = index === active.index
            return (
              <div key={`${source.filename}-${source.chunk_index}`} ref={selected ? selectedRef : undefined}>
                <SourceCard
                  source={source}
                  number={index + 1}
                  selected={selected}
                  collapsed={!selected}
                  onSelect={() => openCitation(active.messageId, index)}
                />
              </div>
            )
          })}
        </div>
      </aside>
    </>
  )
}
