import { memo, useMemo, type ComponentPropsWithoutRef } from 'react'
import ReactMarkdown, { type Components, type Options } from 'react-markdown'
import type { Chunk } from '../api.ts'
import { remarkCitations } from '../remarkCitations.ts'
import { CitationBadge } from './CitationBadge.tsx'
import styles from './MarkdownContent.module.css'

interface MarkdownContentProps {
  messageId: string
  content: string
  sources: Chunk[]
  streaming?: boolean
}

type SpanProps = ComponentPropsWithoutRef<'span'> & { 'data-citation'?: number | string }

function buildComponents(messageId: string, sources: Chunk[]): Components {
  return {
    span: ({ node: _node, ...props }: SpanProps & { node?: unknown }) => {
      const number = Number(props['data-citation'])
      const source = sources[number - 1]
      if (!source) return <span {...props} />
      return <CitationBadge messageId={messageId} number={number} source={source} />
    },
    a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
  }
}

export const MarkdownContent = memo(function MarkdownContent({
  messageId,
  content,
  sources,
  streaming,
}: MarkdownContentProps) {
  const plugins = useMemo<Options['remarkPlugins']>(
    () => [remarkCitations(sources.length)],
    [sources.length],
  )
  const components = useMemo(() => buildComponents(messageId, sources), [messageId, sources])

  return (
    <div className={`${styles.markdown} ${streaming ? styles.streaming : ''}`}>
      {/* Images are dropped: document text is untrusted and an image URL could leak data. */}
      <ReactMarkdown
        remarkPlugins={plugins}
        components={components}
        disallowedElements={['img']}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
