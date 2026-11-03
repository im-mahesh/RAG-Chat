/**
 * Incremental parser for a Server-Sent Events byte stream.
 *
 * Feed it raw chunks as they arrive from a ReadableStream. A chunk may end in
 * the middle of an event (or of a multi-byte character) and may contain several
 * events; `onData` is called once per complete event with its joined `data:`
 * payload. Call `end()` when the stream finishes to flush a final event that
 * lacks its trailing blank line.
 */
export function createSseParser(onData: (data: string) => void) {
  const decoder = new TextDecoder()
  let buffer = ''

  function dispatch(block: string) {
    const data = block
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n')
    if (data) onData(data)
  }

  function drain() {
    buffer = buffer.replace(/\r\n/g, '\n')
    let end = buffer.indexOf('\n\n')
    while (end !== -1) {
      dispatch(buffer.slice(0, end))
      buffer = buffer.slice(end + 2)
      end = buffer.indexOf('\n\n')
    }
  }

  return {
    push(chunk: Uint8Array) {
      buffer += decoder.decode(chunk, { stream: true })
      drain()
    },
    end() {
      buffer += decoder.decode()
      drain()
      if (buffer.trim()) dispatch(buffer)
      buffer = ''
    },
  }
}
