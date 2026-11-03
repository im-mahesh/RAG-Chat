import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import type { Chunk } from '../api.ts'
import { useChatStore } from '../store.ts'
import { MarkdownContent } from './MarkdownContent.tsx'

function source(filename: string, page: number | null = null): Chunk {
  return {
    document_id: 'd1',
    text: `text of ${filename}`,
    filename,
    page,
    heading: null,
    chunk_index: 0,
    score: 0.8,
  }
}

const SOURCES = [source('report.pdf', 3), source('notes.md')]

function renderAnswer(content: string, sources: Chunk[] = SOURCES) {
  return render(<MarkdownContent messageId="m1" content={content} sources={sources} />)
}

beforeEach(() => {
  useChatStore.setState({ activeCitation: null })
})

describe('MarkdownContent citations', () => {
  it('renders [n] markers as clickable badges that open the matching source', () => {
    renderAnswer('Revenue grew [1] and launch is in May [2].')

    const first = screen.getByRole('button', { name: 'Source 1: report.pdf' })
    expect(first.textContent).toBe('1')
    expect(screen.getByRole('button', { name: 'Source 2: notes.md' })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Source 2: notes.md' }))
    expect(useChatStore.getState().activeCitation).toEqual({ messageId: 'm1', index: 1 })
  })

  it('renders a citation with no matching source as plain text, not a button', () => {
    renderAnswer('Only two sources exist [1] but this cites [5].')

    expect(screen.getAllByRole('button')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /Source 5/ })).toBeNull()
    expect(document.body.textContent).toContain('this cites [5].')
  })

  it('keeps citations working inside Markdown formatting', () => {
    renderAnswer('**Revenue grew** [1]\n\n- first point [2]\n- second point')

    expect(document.querySelector('strong')?.textContent).toBe('Revenue grew')
    expect(document.querySelectorAll('li')).toHaveLength(2)
    expect(document.querySelector('li button')?.textContent).toBe('2')
  })

  it('does not turn [n] inside code into badges', () => {
    renderAnswer('Use `items[1]` here.\n\n```\nvalues[2]\n```')

    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(document.querySelector('code')?.textContent).toBe('items[1]')
    expect(document.querySelector('pre')?.textContent).toContain('values[2]')
  })

  it('drops images from untrusted answers and opens links in a new tab', () => {
    renderAnswer('![tracker](https://evil.example/x.png) [docs](https://example.com)')

    expect(document.querySelector('img')).toBeNull()
    const link = screen.getByRole('link', { name: 'docs' })
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
  })
})
