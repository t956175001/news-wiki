export type RunStatus = 'running' | 'success' | 'partial' | 'failed'
export type RunTrigger = 'cron' | 'manual' | 'seed'

export interface ExtractionRunListItem {
  run_id: string
  status: RunStatus
  trigger: RunTrigger
  articles_in: number
  entities_saved: number
  concepts_saved: number
  linkages_saved: number
  total_tokens: number
  // DecimalField serializes as a string.
  cost_cny: string
  elapsed_ms: number
  error_message: string
  started_at: string
  finished_at: string | null
}

export interface StepMetric {
  status: 'done' | 'failed'
  elapsed_ms: number
  error_message?: string
  attempts?: number
  prompt_tokens?: number
  completion_tokens?: number
  count?: number
  fetched?: number
  deduped?: number
  saved?: number
  entities?: number
  concepts?: number
  linkages?: number
}

export interface StepMetrics {
  ingest?: StepMetric
  extract_entities?: StepMetric
  extract_concepts?: StepMetric
  extract_linkages?: StepMetric
  persist?: StepMetric
  brief?: StepMetric
}

export interface ExtractionRunDetail extends ExtractionRunListItem {
  prompt_tokens: number
  completion_tokens: number
  step_metrics: StepMetrics
  prompt_versions: Record<string, number>
}

export interface Stats {
  window_days: number
  since: string
  total_runs: number
  success_runs: number
  success_rate: number
  total_tokens: number
  total_cost_cny: string
  by_status: Record<string, number>
}
