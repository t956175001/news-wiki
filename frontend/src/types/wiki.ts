export type EntityType = 'person' | 'org' | 'product' | 'model' | 'tech' | 'event' | 'other'

export interface EntitySummary {
  id: number
  name: string
  entity_type: EntityType
  entity_type_display: string
  aliases: string[]
  summary: string
  confidence: number
  mention_count: number
  first_seen_at: string | null
  last_seen_at: string | null
}

export interface ConceptSummary {
  id: number
  name: string
  namespace: string
  definition: string
  signals: string[]
  confidence: number
}

export interface EvidenceArticle {
  id: number
  title: string
  url: string
  publish_time: string | null
  source_name: string | null
}

/** Section 4.1 `linkages[].evidences[]`. */
export interface Evidence {
  id: number
  snippet: string
  prompt_key: string
  prompt_version: number
  run_id: string
  article: EvidenceArticle
}

export type LinkageDirection = 'out' | 'in'
export type LinkageObjectKind = 'entity' | 'concept'

/** Discriminated on `kind`: entities carry `entity_type`, concepts carry `namespace`. */
export interface LinkageObject {
  kind: LinkageObjectKind
  id: number
  name: string
  entity_type?: EntityType
  namespace?: string
}

/** One relation as the entry page renders it. Section 4.1 `linkages[]`. */
export interface LinkageWithEvidence {
  id: number
  direction: LinkageDirection
  predicate: string
  object: LinkageObject
  confidence: number
  evidences: Evidence[]
}

/** `GET /api/v1/wiki/entities/{id}/` — section 4.1, the entry page's only data source. */
export interface EntityDetail extends EntitySummary {
  linkages: LinkageWithEvidence[]
}

export interface ConceptDetail extends ConceptSummary {
  linkages: LinkageWithEvidence[]
}

export interface GraphNode {
  id: string
  name: string
  category: string
  value: number
  // Not snake_case on purpose: this is the literal ECharts `graph` series key.
  symbolSize: number
}

export interface GraphLink {
  source: string
  target: string
  predicate: string
  value: number
}

export interface GraphCategory {
  name: string
}

/** `GET /api/v1/wiki/graph/` — section 4.2, aligned to ECharts `graph` series verbatim. */
export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
  categories: GraphCategory[]
  truncated: boolean
}

export interface ExtractRequest {
  article_ids: number[]
}

export interface RunAccepted {
  run_id: string
  status: string
}
