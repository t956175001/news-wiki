import client from './client'
import type { PromptTemplate } from '@/types/prompts'

/** PromptTemplateListView has pagination_class = None: this is a plain array. */
export async function listPrompts(): Promise<PromptTemplate[]> {
  const { data } = await client.get<PromptTemplate[]>('/prompts/')
  return data
}
