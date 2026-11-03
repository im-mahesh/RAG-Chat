import { describe, expect, it } from 'vitest'
import { recentHistory } from './history.ts'
import type { ChatMessage } from './store.ts'

let nextId = 0
function message(role: ChatMessage['role'], content: string, extra: Partial<ChatMessage> = {}) {
  return { id: String(nextId++), role, content, ...extra } satisfies ChatMessage
}

describe('recentHistory', () => {
  it('returns the last four messages, oldest first', () => {
    const messages = Array.from({ length: 7 }, (_, i) =>
      message(i % 2 === 0 ? 'user' : 'assistant', `m${i}`),
    )
    expect(recentHistory(messages).map((m) => m.content)).toEqual(['m3', 'm4', 'm5', 'm6'])
  })

  it('returns everything when there are fewer than four messages', () => {
    expect(recentHistory([message('user', 'hi')])).toEqual([{ role: 'user', content: 'hi' }])
    expect(recentHistory([])).toEqual([])
  })

  it('skips error notices and assistant placeholders with no text yet', () => {
    const messages = [
      message('user', 'q1'),
      message('assistant', 'a1'),
      message('user', 'q2'),
      message('error', 'Cannot reach the API'),
      message('assistant', '', { streaming: true }),
    ]
    expect(recentHistory(messages)).toEqual([
      { role: 'user', content: 'q1' },
      { role: 'assistant', content: 'a1' },
      { role: 'user', content: 'q2' },
    ])
  })

  it('keeps a stopped answer that already has text, and sends only role and content', () => {
    const messages = [message('assistant', 'partial answer', { stopped: true, sources: [] })]
    expect(recentHistory(messages)).toEqual([{ role: 'assistant', content: 'partial answer' }])
  })
})
