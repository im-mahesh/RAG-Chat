import { parseCitations, type CitationSegment } from './citations.ts'

/** The slice of an mdast node this plugin touches. */
interface MdNode {
  type: string
  value?: string
  children?: MdNode[]
  data?: { hName: string; hProperties: Record<string, unknown> }
}

/** Nodes whose text must stay literal (code, link labels, raw HTML). */
const LITERAL_NODES = new Set(['code', 'inlineCode', 'link', 'linkReference', 'definition', 'html'])

function toNode(segment: CitationSegment): MdNode {
  if (segment.type === 'text') return { type: 'text', value: segment.value }
  return {
    type: 'citation',
    data: { hName: 'span', hProperties: { dataCitation: segment.number } },
    children: [{ type: 'text', value: String(segment.number) }],
  }
}

function splitTextNode(node: MdNode, sourceCount: number): MdNode[] {
  const segments = parseCitations(node.value ?? '', sourceCount)
  if (segments.every((segment) => segment.type === 'text')) return [node]
  return segments.map(toNode)
}

function transform(node: MdNode, sourceCount: number) {
  if (!node.children || LITERAL_NODES.has(node.type)) return
  node.children = node.children.flatMap((child) => {
    if (child.type === 'text') return splitTextNode(child, sourceCount)
    transform(child, sourceCount)
    return [child]
  })
}

/**
 * Remark plugin: turns [n] markers in Markdown text into
 * `<span data-citation="n">n</span>` elements, which MarkdownContent renders
 * as citation badges. Working on the parsed tree (rather than the raw string)
 * keeps `arr[1]` in code spans and link labels untouched.
 */
export function remarkCitations(sourceCount: number) {
  return () => (tree: MdNode) => transform(tree, sourceCount)
}
