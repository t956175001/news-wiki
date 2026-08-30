import { marked } from 'marked'
import DOMPurify from 'dompurify'

/** `[n]` -> a clickable anchor jumping to the reference list entry `#cite-n`. */
export function linkifyCitations(html: string): string {
  return html.replace(/\[(\d+)\]/g, '<a href="#cite-$1" class="cite">[$1]</a>')
}

/**
 * Markdown -> sanitized HTML. `marked` does not sanitize its own output (the
 * option was removed upstream); DOMPurify runs on every render because
 * `content_md` is LLM-generated and therefore untrusted.
 */
export function renderMarkdown(markdown: string): string {
  const rawHtml = marked.parse(markdown, { async: false })
  return DOMPurify.sanitize(rawHtml)
}

export function renderBriefContent(markdown: string): string {
  return linkifyCitations(renderMarkdown(markdown))
}
