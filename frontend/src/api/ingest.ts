import client from './client'
import type { Paginated } from '@/types/common'
import type {
  CreateRssSourceRequest,
  RawArticleDetail,
  RawArticleListItem,
  RssSource,
} from '@/types/ingest'

export interface ListArticlesParams {
  source?: number
  extract_status?: string
  search?: string
  page?: number
  page_size?: number
}

/** RssSourceViewSet has `pagination_class = None`: this is a plain array. */
export async function listRssSources(): Promise<RssSource[]> {
  const { data } = await client.get<RssSource[]>('/ingest/sources/')
  return data
}

export async function createRssSource(payload: CreateRssSourceRequest): Promise<RssSource> {
  const { data } = await client.post<RssSource>('/ingest/sources/', payload)
  return data
}

export async function listArticles(
  params: ListArticlesParams = {},
): Promise<Paginated<RawArticleListItem>> {
  const { data } = await client.get<Paginated<RawArticleListItem>>('/ingest/articles/', { params })
  return data
}

export async function getArticle(id: number): Promise<RawArticleDetail> {
  const { data } = await client.get<RawArticleDetail>(`/ingest/articles/${id}/`)
  return data
}
