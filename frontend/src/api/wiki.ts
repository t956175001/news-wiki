import client from './client'
import type { Paginated } from '@/types/common'
import type {
  ConceptDetail,
  ConceptSummary,
  EntityDetail,
  EntitySummary,
  ExtractRequest,
  GraphData,
  RunAccepted,
} from '@/types/wiki'

export interface ListEntitiesParams {
  entity_type?: string
  search?: string
  ordering?: string
  page?: number
  page_size?: number
}

export interface ListConceptsParams {
  namespace?: string
  search?: string
  page?: number
  page_size?: number
}

export interface GraphParams {
  entity_type?: string
  namespace?: string
  limit?: number
}

export async function listEntities(
  params: ListEntitiesParams = {},
): Promise<Paginated<EntitySummary>> {
  const { data } = await client.get<Paginated<EntitySummary>>('/wiki/entities/', { params })
  return data
}

export async function getEntity(id: number): Promise<EntityDetail> {
  const { data } = await client.get<EntityDetail>(`/wiki/entities/${id}/`)
  return data
}

export async function listConcepts(
  params: ListConceptsParams = {},
): Promise<Paginated<ConceptSummary>> {
  const { data } = await client.get<Paginated<ConceptSummary>>('/wiki/concepts/', { params })
  return data
}

export async function getConcept(id: number): Promise<ConceptDetail> {
  const { data } = await client.get<ConceptDetail>(`/wiki/concepts/${id}/`)
  return data
}

export async function getGraph(params: GraphParams = {}): Promise<GraphData> {
  const { data } = await client.get<GraphData>('/wiki/graph/', { params })
  return data
}

export async function triggerExtract(payload: ExtractRequest): Promise<RunAccepted> {
  const { data } = await client.post<RunAccepted>('/wiki/extract/', payload)
  return data
}
