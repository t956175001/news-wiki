export type ExtractStatus = 'pending' | 'extracted' | 'failed' | 'skipped'

export interface RssSource {
  id: number
  name: string
  url: string
  site_url: string
  enabled: boolean
  last_fetched_at: string | null
  last_error: string
  article_count: number
  created_at: string
}

export interface CreateRssSourceRequest {
  name: string
  url: string
  site_url?: string
  enabled?: boolean
}

export interface RawArticleListItem {
  id: number
  source: number | null
  source_name: string | null
  title: string
  url: string
  summary: string
  author: string
  publish_time: string | null
  lang: string
  extract_status: ExtractStatus
  fetched_at: string
}

export interface RawArticleDetail extends RawArticleListItem {
  content: string
  content_hash: string
}
