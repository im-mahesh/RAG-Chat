export type CitationSegment =
  | { type: 'text'; value: string }
  | { type: 'citation'; number: number }

/** Matches [1] and grouped markers such as [1, 2]. */
const MARKER = /\[(\d+(?:\s*,\s*\d+)*)\]/g

/**
 * Splits text into plain text and citation markers.
 *
 * Only numbers from 1 to `sourceCount` become citations. A marker that points
 * at a source which doesn't exist (e.g. [7] with 3 sources) stays plain text,
 * so the UI never links to something that isn't there.
 */
export function parseCitations(text: string, sourceCount: number): CitationSegment[] {
  const segments: CitationSegment[] = []

  function pushText(value: string) {
    if (!value) return
    const last = segments.at(-1)
    if (last?.type === 'text') last.value += value
    else segments.push({ type: 'text', value })
  }

  let cursor = 0
  for (const match of text.matchAll(MARKER)) {
    pushText(text.slice(cursor, match.index))
    for (const raw of match[1].split(',').map((part) => part.trim())) {
      const number = Number(raw)
      if (number >= 1 && number <= sourceCount) segments.push({ type: 'citation', number })
      else pushText(`[${raw}]`)
    }
    cursor = match.index + match[0].length
  }
  pushText(text.slice(cursor))
  return segments
}
