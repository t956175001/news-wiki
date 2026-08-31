import { describe, expect, it } from 'vitest'
import { escapeHtml } from './escapeHtml'

describe('escapeHtml', () => {
  it('neutralises a script tag smuggled in through an entity name', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('escapes the ampersand first so entities are not double-encoded', () => {
    expect(escapeHtml('A&B <tag>')).toBe('A&amp;B &lt;tag&gt;')
  })

  it('escapes both quote characters, for values landing inside an attribute', () => {
    expect(escapeHtml(`say "hi" it's me`)).toBe('say &quot;hi&quot; it&#39;s me')
  })

  it('leaves ordinary text — including CJK — untouched', () => {
    expect(escapeHtml('智谱 GLM-5.3 发布')).toBe('智谱 GLM-5.3 发布')
  })

  it('handles an empty string', () => {
    expect(escapeHtml('')).toBe('')
  })
})
