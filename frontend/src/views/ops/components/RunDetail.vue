<script setup lang="ts">
import { computed } from 'vue'
import type { StepMetric, StepMetrics } from '@/types/ops'

const props = defineProps<{ stepMetrics: StepMetrics }>()

const STEPS: { key: keyof StepMetrics; label: string }[] = [
  { key: 'ingest', label: '采集' },
  { key: 'extract_entities', label: '抽取实体' },
  { key: 'extract_concepts', label: '抽取概念' },
  { key: 'extract_linkages', label: '抽取关系' },
  { key: 'persist', label: '落库' },
  { key: 'brief', label: '生成简报' },
]

interface StepRow {
  key: keyof StepMetrics
  label: string
  metric: StepMetric | undefined
}

const rows = computed<StepRow[]>(() =>
  STEPS.map((step) => ({ ...step, metric: props.stepMetrics[step.key] })),
)

function tokensFor(metric: StepMetric): number | null {
  if (metric.prompt_tokens === undefined && metric.completion_tokens === undefined) return null
  return (metric.prompt_tokens ?? 0) + (metric.completion_tokens ?? 0)
}

function outputFor(key: keyof StepMetrics, metric: StepMetric): string {
  switch (key) {
    case 'ingest':
      return `拉取 ${metric.fetched ?? 0} · 去重 ${metric.deduped ?? 0} · 入库 ${metric.saved ?? 0}`
    case 'extract_entities':
    case 'extract_concepts':
    case 'extract_linkages':
      return `抽取 ${metric.count ?? 0} 条`
    case 'persist':
      return `实体 ${metric.entities ?? 0} · 概念 ${metric.concepts ?? 0} · 关系 ${metric.linkages ?? 0}`
    default:
      return ''
  }
}
</script>

<template>
  <ol class="run-detail">
    <li
      v-for="row in rows"
      :key="row.key"
      class="run-detail__step"
      :class="{
        'run-detail__step--pending': !row.metric,
        'run-detail__step--failed': row.metric?.status === 'failed',
      }"
    >
      <span class="run-detail__icon" aria-hidden="true">
        <template v-if="!row.metric">–</template>
        <template v-else-if="row.metric.status === 'failed'">✕</template>
        <template v-else>✓</template>
      </span>

      <div class="run-detail__body">
        <div class="run-detail__label-row">
          <span class="run-detail__label">{{ row.label }}</span>
          <span v-if="!row.metric" class="run-detail__pending-text">未执行</span>
          <template v-else>
            <span class="run-detail__elapsed mono">{{ row.metric.elapsed_ms }}ms</span>
            <span v-if="tokensFor(row.metric) !== null" class="run-detail__tokens mono">
              {{ tokensFor(row.metric) }} tokens
            </span>
            <span v-if="row.metric.attempts !== undefined" class="run-detail__attempts mono">
              尝试 {{ row.metric.attempts }} 次
            </span>
          </template>
        </div>

        <p v-if="row.metric && outputFor(row.key, row.metric)" class="run-detail__output">
          {{ outputFor(row.key, row.metric) }}
        </p>

        <pre v-if="row.metric?.status === 'failed'" class="run-detail__error mono">{{
          row.metric.error_message
        }}</pre>
      </div>
    </li>
  </ol>
</template>

<style scoped lang="scss">
.run-detail {
  list-style: none;
  margin: 0;
  padding: var(--space-3) 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.run-detail__step {
  display: flex;
  gap: var(--space-3);
}

.run-detail__icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #fff;
  background: var(--color-success);
}

.run-detail__step--failed .run-detail__icon {
  background: var(--color-danger);
}

.run-detail__step--pending .run-detail__icon {
  background: var(--color-border);
  color: var(--color-text-muted);
}

.run-detail__step--pending {
  opacity: 0.55;
}

.run-detail__body {
  flex: 1;
  min-width: 0;
}

.run-detail__label-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.run-detail__label {
  font-size: 13px;
  font-weight: 600;
}

.run-detail__pending-text,
.run-detail__elapsed,
.run-detail__tokens,
.run-detail__attempts {
  font-size: 12px;
  color: var(--color-text-muted);
}

.run-detail__output {
  margin: var(--space-1) 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
}

.run-detail__error {
  margin: var(--space-2) 0 0;
  padding: var(--space-2) var(--space-3);
  background: var(--color-danger-soft);
  color: var(--color-danger);
  border-radius: var(--radius-sm);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  user-select: text;
}
</style>
