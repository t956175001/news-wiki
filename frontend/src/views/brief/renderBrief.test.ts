import { describe, it, expect } from 'vitest'
import { linkifyCitations, renderMarkdown, renderBriefContent } from './renderBrief'

describe('linkifyCitations', () => {
  it('turns [n] markers into anchors pointing at the reference list', () => {
    const html = '<p>OpenAI 发布了 GPT-5[1]，采用了 MoE 架构[3]。</p>'
    const result = linkifyCitations(html)
    expect(result).toContain('<a href="#cite-1" class="cite">[1]</a>')
    expect(result).toContain('<a href="#cite-3" class="cite">[3]</a>')
  })

  it('leaves text without citation markers unchanged', () => {
    const html = '<p>没有引用的一句话。</p>'
    expect(linkifyCitations(html)).toBe(html)
  })
})

describe('renderMarkdown', () => {
  it('renders markdown to HTML', () => {
    const result = renderMarkdown('**加粗** 与 [1] 角标')
    expect(result).toContain('<strong>加粗</strong>')
  })

  it('strips script tags from untrusted markdown content', () => {
    const malicious = '正常内容 <script>alert(1)</script> 之后的内容'
    const result = renderMarkdown(malicious)
    expect(result).not.toContain('<script')
    expect(result).not.toContain('alert(1)')
  })

  it('strips inline event-handler XSS vectors too', () => {
    const malicious = '<img src=x onerror="alert(1)">'
    const result = renderMarkdown(malicious)
    expect(result).not.toContain('onerror')
  })
})

describe('renderBriefContent', () => {
  it('produces sanitized HTML with citation anchors, end to end', () => {
    const md = 'OpenAI 发布了 GPT-5[1]。 <script>alert(1)</script>'
    const result = renderBriefContent(md)
    expect(result).toContain('href="#cite-1"')
    expect(result).not.toContain('<script')
  })
})
