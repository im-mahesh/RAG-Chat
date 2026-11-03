import { useEffect, useRef, useState } from 'react'
import styles from './ChatInput.module.css'

const MAX_HEIGHT_PX = 160

interface ChatInputProps {
  disabled: boolean
  streaming: boolean
  placeholder: string
  onSend: (text: string) => void
  onStop: () => void
}

export function ChatInput({ disabled, streaming, placeholder, onSend, onStop }: ChatInputProps) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`
  }, [text])

  useEffect(() => {
    if (!disabled) ref.current?.focus()
  }, [disabled])

  function submit() {
    const question = text.trim()
    if (!question || disabled) return
    onSend(question)
    setText('')
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <textarea
        ref={ref}
        className={styles.input}
        value={text}
        rows={1}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Message"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      {streaming ? (
        <button type="button" className={`${styles.send} ${styles.stop}`} onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className={styles.send} disabled={disabled || text.trim() === ''}>
          Send
        </button>
      )}
    </form>
  )
}
