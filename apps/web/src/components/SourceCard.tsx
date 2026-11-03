import type { Chunk } from '../api.ts'
import { formatScore } from '../sources.ts'
import styles from './SourceCard.module.css'

interface SourceCardProps {
  source: Chunk
  /** 1-based, matching the [n] markers in the answer. */
  number: number
  selected?: boolean
  /** Show only the header. Requires `onSelect` so the card can be expanded. */
  collapsed?: boolean
  onSelect?: () => void
}

function Header({ source, number }: Pick<SourceCardProps, 'source' | 'number'>) {
  const details = [
    source.page != null ? `page ${source.page}` : null,
    source.heading,
    formatScore(source.score),
  ].filter(Boolean)
  return (
    <>
      <span className={styles.number}>[{number}]</span>
      <span className={styles.heading}>
        <span className={styles.filename}>{source.filename}</span>
        <span className={styles.meta}>{details.join(' · ')}</span>
      </span>
    </>
  )
}

export function SourceCard({ source, number, selected, collapsed, onSelect }: SourceCardProps) {
  const className = `${styles.card} ${selected ? styles.selected : ''}`
  if (collapsed) {
    return (
      <button type="button" className={`${className} ${styles.collapsed}`} onClick={onSelect}>
        <Header source={source} number={number} />
      </button>
    )
  }
  return (
    <article className={className} aria-current={selected ? 'true' : undefined}>
      <div className={styles.header}>
        <Header source={source} number={number} />
      </div>
      <p className={styles.text}>{source.text}</p>
    </article>
  )
}
