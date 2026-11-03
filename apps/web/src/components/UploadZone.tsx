import { useRef, useState } from 'react'
import { useUploadDocuments, type UploadProgress } from '../hooks/useDocuments.ts'
import { ACCEPT_ATTRIBUTE } from '../upload.ts'
import styles from './UploadZone.module.css'

export function UploadZone() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<UploadProgress | null>(null)
  const upload = useUploadDocuments()
  const failures = upload.data ?? []

  function startUpload(fileList: FileList | null) {
    const files = Array.from(fileList ?? [])
    if (files.length === 0 || upload.isPending) return
    upload.mutate({ files, onProgress: setProgress })
  }

  function handleDrop(event: React.DragEvent) {
    event.preventDefault()
    setDragging(false)
    startUpload(event.dataTransfer.files)
  }

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    startUpload(event.target.files)
    event.target.value = ''
  }

  return (
    <div>
      <div
        className={`${styles.zone} ${dragging ? styles.dragging : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          onChange={handleChange}
          className={styles.input}
          aria-label="Upload documents"
          data-testid="file-input"
        />
        {upload.isPending && progress ? (
          <p className={styles.status} role="status">
            <span className={styles.spinner} aria-hidden="true" />
            Indexing {progress.done + 1} of {progress.total}: {progress.current}
          </p>
        ) : (
          <>
            <p className={styles.hint}>Drop PDF, Markdown or text files here</p>
            <button type="button" className={styles.button} onClick={() => inputRef.current?.click()}>
              Choose files
            </button>
          </>
        )}
      </div>
      {failures.length > 0 && (
        <ul className={styles.errors} role="alert">
          {failures.map((failure, index) => (
            <li key={`${failure.filename}-${index}`}>
              <strong>{failure.filename}</strong>: {failure.message}
            </li>
          ))}
          <li>
            <button type="button" className={styles.dismiss} onClick={() => upload.reset()}>
              Dismiss
            </button>
          </li>
        </ul>
      )}
    </div>
  )
}
