import { useEffect } from 'react'
import { useDeleteDocument, useDocuments } from '../hooks/useDocuments.ts'
import { useChatStore } from '../store.ts'
import styles from './DocumentList.module.css'

export function DocumentList() {
  const { data: documents, isPending, error, refetch } = useDocuments()
  const remove = useDeleteDocument()
  const selected = useChatStore((state) => state.selectedDocumentIds)
  const toggleDocument = useChatStore((state) => state.toggleDocument)
  const pruneSelection = useChatStore((state) => state.pruneSelection)

  useEffect(() => {
    if (documents) pruneSelection(documents.map((doc) => doc.id))
  }, [documents, pruneSelection])

  if (isPending) return <p className={styles.note}>Loading documents…</p>
  if (error) {
    return (
      <p className={`${styles.note} ${styles.error}`} role="alert">
        {error.message}{' '}
        <button type="button" className={styles.link} onClick={() => refetch()}>
          Retry
        </button>
      </p>
    )
  }
  if (documents.length === 0) return <p className={styles.note}>No documents yet.</p>

  return (
    <ul className={styles.list}>
      {documents.map((doc) => {
        const deleting = remove.isPending && remove.variables === doc.id
        return (
          <li key={doc.id} className={`${styles.item} ${deleting ? styles.deleting : ''}`}>
            <label className={styles.label} title={doc.filename}>
              <input
                type="checkbox"
                checked={selected.includes(doc.id)}
                onChange={() => toggleDocument(doc.id)}
                aria-label={`Search only ${doc.filename}`}
              />
              <span className={styles.text}>
                <span className={styles.name}>{doc.filename}</span>
                <span className={styles.meta}>
                  {doc.chunk_count} {doc.chunk_count === 1 ? 'chunk' : 'chunks'}
                </span>
              </span>
            </label>
            <button
              type="button"
              className={styles.delete}
              onClick={() => remove.mutate(doc.id)}
              disabled={deleting}
              aria-label={`Delete ${doc.filename}`}
              title="Delete"
            >
              ×
            </button>
          </li>
        )
      })}
      {remove.isError && (
        <li className={`${styles.note} ${styles.error}`} role="alert">
          {remove.error.message}
        </li>
      )}
    </ul>
  )
}
