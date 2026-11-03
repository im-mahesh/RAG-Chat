import { useMutation } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { streamChat, type HistoryMessage, type StreamEvent } from '../api.ts'
import { recentHistory } from '../history.ts'
import { useChatStore } from '../store.ts'

interface StreamVariables {
  question: string
  documentIds: string[]
  history: HistoryMessage[]
  assistantId: string
  signal: AbortSignal
}

function applyEvent(assistantId: string, event: StreamEvent): string | null {
  const { updateMessage, appendToMessage } = useChatStore.getState()
  switch (event.type) {
    case 'sources':
      updateMessage(assistantId, { sources: event.sources })
      return null
    case 'token':
      appendToMessage(assistantId, event.text)
      return null
    case 'error':
      return event.message
    case 'done':
      return null
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/** Ends the assistant message; reports a failure as a separate error message. */
function finishMessage(assistantId: string, failure: string | null, stopped: boolean) {
  const { messages, updateMessage, removeMessage, addMessage } = useChatStore.getState()
  const message = messages.find((m) => m.id === assistantId)
  if (message && message.content === '' && failure) {
    removeMessage(assistantId)
  } else {
    updateMessage(assistantId, { streaming: false, stopped })
  }
  if (failure) addMessage({ role: 'error', content: failure })
}

async function runStream({ question, documentIds, history, assistantId, signal }: StreamVariables) {
  let streamError: string | null = null
  try {
    await streamChat(
      { question, document_ids: documentIds.length > 0 ? documentIds : null, history },
      signal,
      (event) => {
        streamError = applyEvent(assistantId, event) ?? streamError
      },
    )
  } catch (error) {
    if (isAbort(error)) return finishMessage(assistantId, null, true)
    streamError = (error as Error).message
  }
  finishMessage(assistantId, streamError, false)
}

export function useAsk() {
  const controllerRef = useRef<AbortController | null>(null)
  const mutation = useMutation({ mutationFn: runStream })

  useEffect(() => () => controllerRef.current?.abort(), [])

  function ask(question: string) {
    const { addMessage, selectedDocumentIds, messages } = useChatStore.getState()
    const history = recentHistory(messages) // before the new question is added
    addMessage({ role: 'user', content: question })
    const assistantId = addMessage({ role: 'assistant', content: '', streaming: true })
    const controller = new AbortController()
    controllerRef.current = controller
    mutation.mutate({
      question,
      documentIds: selectedDocumentIds,
      history,
      assistantId,
      signal: controller.signal,
    })
  }

  function stop() {
    controllerRef.current?.abort()
  }

  return { ask, stop, isStreaming: mutation.isPending }
}
