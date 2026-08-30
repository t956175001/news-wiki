<script setup lang="ts">
import { computed, reactive } from 'vue'
import EvidenceCard from './EvidenceCard.vue'
import type { LinkageWithEvidence } from '@/types/wiki'

const props = defineProps<{
  linkages: LinkageWithEvidence[]
}>()

interface PredicateGroup {
  predicate: string
  linkages: LinkageWithEvidence[]
}

// Groups by first-occurrence order rather than sorting alphabetically: the
// backend already orders by predicate then confidence (see linkage_payload),
// so preserving array order keeps that ranking intact within each group.
const groups = computed<PredicateGroup[]>(() => {
  const byPredicate = new Map<string, LinkageWithEvidence[]>()
  for (const linkage of props.linkages) {
    const bucket = byPredicate.get(linkage.predicate)
    if (bucket) {
      bucket.push(linkage)
    } else {
      byPredicate.set(linkage.predicate, [linkage])
    }
  }
  return Array.from(byPredicate.entries()).map(([predicate, items]) => ({
    predicate,
    linkages: items,
  }))
})

const expanded = reactive(new Set<number>())

function toggle(linkageId: number) {
  if (expanded.has(linkageId)) {
    expanded.delete(linkageId)
  } else {
    expanded.add(linkageId)
  }
}

function percent(confidence: number) {
  return Math.round(confidence * 100)
}
</script>

<template>
  <div class="linkage-group">
    <section v-for="group in groups" :key="group.predicate" class="linkage-group__section">
      <h3 class="linkage-group__predicate">
        {{ group.predicate }}
        <span class="linkage-group__count mono">{{ group.linkages.length }}</span>
      </h3>

      <ul class="linkage-group__list">
        <li v-for="linkage in group.linkages" :key="linkage.id" class="linkage-row">
          <div class="linkage-row__main">
            <span
              class="linkage-row__direction"
              :aria-label="linkage.direction === 'out' ? '流出关系' : '流入关系'"
            >
              {{ linkage.direction === 'out' ? '→' : '←' }}
            </span>

            <RouterLink
              v-if="linkage.object.kind === 'entity'"
              :to="`/wiki/${linkage.object.id}`"
              class="linkage-row__object"
            >
              {{ linkage.object.name }}
            </RouterLink>
            <span v-else class="linkage-row__object linkage-row__object--concept">
              {{ linkage.object.name }}
              <span v-if="linkage.object.namespace" class="linkage-row__namespace mono">{{
                linkage.object.namespace
              }}</span>
            </span>

            <span class="linkage-row__confidence mono">{{ percent(linkage.confidence) }}%</span>

            <button
              type="button"
              class="linkage-row__toggle"
              :aria-expanded="expanded.has(linkage.id)"
              @click="toggle(linkage.id)"
            >
              {{ expanded.has(linkage.id) ? '收起证据 −' : '展开证据 +' }}
            </button>
          </div>

          <div v-if="expanded.has(linkage.id)" class="linkage-row__evidences">
            <EvidenceCard
              v-for="evidence in linkage.evidences"
              :key="evidence.id"
              :evidence="evidence"
              :confidence="linkage.confidence"
            />
            <p v-if="linkage.evidences.length === 0" class="linkage-row__no-evidence">
              暂无原文证据
            </p>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped lang="scss">
.linkage-group__section + .linkage-group__section {
  margin-top: var(--space-5);
}

.linkage-group__predicate {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  font-size: 15px;
  font-family: var(--font-display);
  color: var(--color-text);
  margin-bottom: var(--space-2);
}

.linkage-group__count {
  font-size: 11px;
  color: var(--color-text-muted);
}

.linkage-group__list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--color-border);
}

.linkage-row {
  border-bottom: 1px solid var(--color-border);
}

.linkage-row__main {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-1);
}

.linkage-row__direction {
  color: var(--color-accent-strong);
  font-family: var(--font-mono);
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

.linkage-row__object {
  color: var(--color-text);
  font-weight: 600;
  text-decoration: none;

  &:hover {
    color: var(--color-accent-strong);
    text-decoration: underline;
  }
}

.linkage-row__object--concept {
  font-weight: 500;
  color: var(--color-text);
  cursor: default;
}

.linkage-row__namespace {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-left: var(--space-1);
}

.linkage-row__confidence {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-left: auto;
}

.linkage-row__toggle {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  padding: 2px var(--space-3);
  font-size: 12px;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-standard);

  &:hover {
    border-color: var(--color-accent);
    color: var(--color-accent-strong);
  }
}

.linkage-row__evidences {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0 var(--space-1) var(--space-4) calc(16px + var(--space-3));
}

.linkage-row__no-evidence {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
