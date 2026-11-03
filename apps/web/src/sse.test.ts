import { describe, expect, it } from 'vitest'
import { createSseParser } from './sse.ts'

const encoder = new TextEncoder()

function parse(chunks: Uint8Array[]): string[] {
  const events: string[] = []
  const parser = createSseParser((data) => events.push(data))
  chunks.forEach((chunk) => parser.push(chunk))
  parser.end()
  return events
}

const TOKEN = '{"type":"token","text":"héllo 🌍"}'
const STREAM = encoder.encode(`data: ${TOKEN}\n\ndata: {"type":"done"}\n\n`)

describe('createSseParser', () => {
  it('emits several events delivered in one chunk', () => {
    expect(parse([encoder.encode('data: {"a":1}\n\ndata: {"a":2}\n\n')])).toEqual([
      '{"a":1}',
      '{"a":2}',
    ])
  })

  it('reassembles events split at every possible byte boundary', () => {
    for (let split = 1; split < STREAM.length; split++) {
      const events = parse([STREAM.slice(0, split), STREAM.slice(split)])
      expect(events, `split at byte ${split}`).toEqual([TOKEN, '{"type":"done"}'])
    }
  })

  it('handles one byte at a time, including multi-byte characters', () => {
    const bytes = Array.from(STREAM, (byte) => new Uint8Array([byte]))
    expect(parse(bytes)).toEqual([TOKEN, '{"type":"done"}'])
  })

  it('supports CRLF (even split across reads), comments and multi-line data', () => {
    const events = parse([
      encoder.encode('data: x\r'),
      encoder.encode('\n\r\n: keep-alive\n\nevent: foo\nid: 1\ndata: a\ndata: b\n\n'),
    ])
    expect(events).toEqual(['x', 'a\nb'])
  })

  it('flushes a final event with no trailing blank line, and never emits partial data early', () => {
    expect(parse([encoder.encode('data:{"x":1}\n\ndata: last')])).toEqual(['{"x":1}', 'last'])

    const events: string[] = []
    createSseParser((data) => events.push(data)).push(encoder.encode('data: partial'))
    expect(events).toEqual([])
  })
})
