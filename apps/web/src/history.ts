import type { HistoryMessage } from './api.ts'
import type { ChatMessage } from './store.ts'

/** How many recent messages are sent with each question so follow-ups can be rewritten. */
export const HISTORY_LIMIT = 4

/**
 * The last few conversation messages, oldest first. Error notices and
 * placeholders that haven't received any text yet are not part of the
 * conversation, so they are skipped.
 */
export function recentHistory(messages: ChatMessage[], limit = HISTORY_LIMIT): HistoryMessage[] {
  return messages
    .flatMap((message) =>
      (message.role === 'user' || message.role === 'assistant') && message.content !== ''
        ? [{ role: message.role, content: message.content }]
        : [],
    )
    .slice(-limit)
}
