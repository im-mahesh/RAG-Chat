import { describe, expect, it } from 'vitest'
import { parseCitations } from './citations.ts'

describe('parseCitations', () => {
  it('splits text around [n] markers', () => {
    expect(parseCitations('Gas giants [1] and ice giants [2].', 2)).toEqual([
      { type: 'text', value: 'Gas giants ' },
      { type: 'citation', number: 1 },
      { type: 'text', value: ' and ice giants ' },
      { type: 'citation', number: 2 },
      { type: 'text', value: '.' },
    ])
  })

  it('keeps a marker with no matching source as plain text', () => {
    expect(parseCitations('Claim [3] and [0] and [7].', 2)).toEqual([
      { type: 'text', value: 'Claim [3] and [0] and [7].' },
    ])
  })

  it('handles grouped and adjacent markers', () => {
    expect(parseCitations('See [1, 2][3]', 3)).toEqual([
      { type: 'text', value: 'See ' },
      { type: 'citation', number: 1 },
      { type: 'citation', number: 2 },
      { type: 'citation', number: 3 },
    ])
  })

  it('only links the valid numbers inside a group', () => {
    expect(parseCitations('[1, 9]', 2)).toEqual([
      { type: 'citation', number: 1 },
      { type: 'text', value: '[9]' },
    ])
  })

  it('leaves text without markers alone', () => {
    expect(parseCitations('no markers, just [text] and arr[i]', 3)).toEqual([
      { type: 'text', value: 'no markers, just [text] and arr[i]' },
    ])
    expect(parseCitations('', 3)).toEqual([])
  })
})
