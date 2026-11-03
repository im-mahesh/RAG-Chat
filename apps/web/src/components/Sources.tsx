import type { Chunk } from '../api.ts'
import { SourceCard } from './SourceCard.tsx'
import styles from './Sources.module.css'

/** Collapsed "Sources (N)" list under an answer, with each source's full details. */
export function Sources({ messageId, sources }: { messageId: string; sources: Chunk[] }) {
  if (sources.length === 0) return null
  return (
    <details className={styles.sources}>
      <summary>Sources ({sources.length})</summary>
      <div className={styles.list}>
        {sources.map((source, index) => (
          <SourceCard
            key={`${messageId}-${source.filename}-${source.chunk_index}`}
            source={source}
            number={index + 1}
          />
        ))}
      </div>
    </details>
  )
}
