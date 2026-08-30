import client from './client'
import type { Paginated } from '@/types/common'
import type { ExtractionRunDetail, ExtractionRunListItem, Stats } from '@/types/ops'

export interface ListRunsParams {
  status?: string
  trigger?: string
  page?: number
  page_size?: number
}

export interface StatsParams {
  days?: number
}

export async function listRuns(
  params: ListRunsParams = {},
): Promise<Paginated<ExtractionRunListItem>> {
  const { data } = await client.get<Paginated<ExtractionRunListItem>>('/ops/runs/', { params })
  return data
}

export async function getRun(runId: string): Promise<ExtractionRunDetail> {
  const { data } = await client.get<ExtractionRunDetail>(`/ops/runs/${runId}/`)
  return data
}

export async function getStats(params: StatsParams = {}): Promise<Stats> {
  const { data } = await client.get<Stats>('/ops/stats/', { params })
  return data
}
