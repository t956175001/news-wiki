import client from './client'
import type { Paginated } from '@/types/common'
import type { DailyBriefDetail, DailyBriefListItem } from '@/types/brief'

export interface ListBriefsParams {
  page?: number
  page_size?: number
}

export async function listBriefs(
  params: ListBriefsParams = {},
): Promise<Paginated<DailyBriefListItem>> {
  const { data } = await client.get<Paginated<DailyBriefListItem>>('/brief/', { params })
  return data
}

export async function getLatestBrief(): Promise<DailyBriefDetail> {
  const { data } = await client.get<DailyBriefDetail>('/brief/latest/')
  return data
}

/** `date` must be `YYYY-MM-DD`. */
export async function getBriefByDate(date: string): Promise<DailyBriefDetail> {
  const { data } = await client.get<DailyBriefDetail>(`/brief/${date}/`)
  return data
}
