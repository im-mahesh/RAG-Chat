import type { Chunk } from './api.ts'

/** "file.pdf · page 3 · Heading" with the parts that exist. */
export function describeSource(chunk: Chunk): string {
  const parts = [chunk.filename]
  if (chunk.page != null) parts.push(`page ${chunk.page}`)
  if (chunk.heading) parts.push(chunk.heading)
  return parts.join(' · ')
}

export function formatScore(score: number): string {
  return `${Math.round(Math.max(0, score) * 100)}% match`
}
