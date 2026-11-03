import { useChatStore } from '../store.ts'
import { DocumentList } from './DocumentList.tsx'
import styles from './Sidebar.module.css'
import { UploadZone } from './UploadZone.tsx'

export function Sidebar() {
  const open = useChatStore((state) => state.sidebarOpen)
  const setOpen = useChatStore((state) => state.setSidebarOpen)
  const selectedCount = useChatStore((state) => state.selectedDocumentIds.length)
  const clearSelection = useChatStore((state) => state.clearSelection)

  return (
    <>
      <button
        type="button"
        className={`${styles.backdrop} ${open ? styles.backdropOpen : ''}`}
        onClick={() => setOpen(false)}
        aria-label="Close documents"
        tabIndex={open ? 0 : -1}
      />
      <aside className={`${styles.sidebar} ${open ? styles.open : ''}`} aria-label="Documents">
        <div className={styles.header}>
          <h2 className={styles.title}>Documents</h2>
          <button
            type="button"
            className={styles.close}
            onClick={() => setOpen(false)}
            aria-label="Close documents"
          >
            ×
          </button>
        </div>
        <UploadZone />
        <div className={styles.filter}>
          <span>{selectedCount === 0 ? 'Searching all documents' : `Searching ${selectedCount} selected`}</span>
          {selectedCount > 0 && (
            <button type="button" className={styles.clear} onClick={clearSelection}>
              Clear
            </button>
          )}
        </div>
        <div className={styles.list}>
          <DocumentList />
        </div>
      </aside>
    </>
  )
}
