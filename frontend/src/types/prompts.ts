export interface PromptVersion {
  id: number
  version_no: number
  text: string
  note: string
  is_default: boolean
  created_at: string
}

export interface PromptTemplate {
  key: string
  name: string
  description: string
  default_text: string
  current_version: PromptVersion | null
  created_at: string
}
