import type { EntityType } from '@/types/wiki'

// Mirrors Entity.ENTITY_TYPES (ARCHITECTURE 3.2) — a fixed backend choices
// field, not something worth a network round trip to discover.
export const ENTITY_TYPE_OPTIONS: { value: EntityType; label: string }[] = [
  { value: 'person', label: 'Person' },
  { value: 'org', label: 'Organization' },
  { value: 'product', label: 'Product' },
  { value: 'model', label: 'Model' },
  { value: 'tech', label: 'Technology' },
  { value: 'event', label: 'Event' },
  { value: 'other', label: 'Other' },
]
