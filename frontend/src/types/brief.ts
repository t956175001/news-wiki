export interface Citation {
  index: number
  raw_article_id: number
  title: string
  url: string
  publish_time: string | null
}

export interface DailyBriefListItem {
  id: number
  date: string
  title: string
  model_name: string
  citation_count: number
  created_at: string
}

export interface DailyBriefDetail {
  id: number
  date: string
  title: string
  content_md: string
  citations: Citation[]
  model_name: string
  run_id: string | null
  created_at: string
}
