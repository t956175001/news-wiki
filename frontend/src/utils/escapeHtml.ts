/**
 * Escape a string for interpolation into HTML.
 *
 * Needed because ECharts renders `tooltip.formatter`'s return value as HTML,
 * and the strings we put in it (entity names, predicates) come from an LLM
 * reading articles we scraped off the public internet. Nothing between the
 * feed and the canvas treats that text as untrusted, so this is where it gets
 * treated as untrusted.
 */
export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
