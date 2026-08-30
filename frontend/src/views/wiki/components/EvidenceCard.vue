<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import type { Evidence } from '@/types/wiki'

const props = defineProps<{
  evidence: Evidence
  /** Not on Evidence itself — the parent Linkage's confidence, shared by every evidence under it. */
  confidence: number
}>()

const percent = computed(() => Math.round(props.confidence * 100))
const publishTime = computed(() =>
  props.evidence.article.publish_time
    ? dayjs(props.evidence.article.publish_time).format('YYYY-MM-DD HH:mm')
    : '发布时间未知',
)
const runIdShort = computed(() => props.evidence.run_id.slice(0, 8))
</script>

<template>
  <article class="evidence-card">
    <blockquote class="evidence-card__snippet mono">{{ evidence.snippet }}</blockquote>

    <div class="evidence-card__source">
      <a
        class="evidence-card__source-link"
        :href="evidence.article.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        {{ evidence.article.title }}
        <svg class="evidence-card__external-icon" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M6 2.5h7v7M13.2 2.8 6.5 9.5M3.5 5H3a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1v-.5"
            fill="none"
            stroke="currentColor"
            stroke-width="1.3"
          />
        </svg>
      </a>
      <span class="evidence-card__dot" aria-hidden="true">·</span>
      <span v-if="evidence.article.source_name" class="evidence-card__meta">{{
        evidence.article.source_name
      }}</span>
      <span v-if="evidence.article.source_name" class="evidence-card__dot" aria-hidden="true"
        >·</span
      >
      <span class="evidence-card__meta mono">{{ publishTime }}</span>
    </div>

    <div class="evidence-card__footer">
      <div class="evidence-card__confidence">
        <a-progress
          class="evidence-card__progress"
          :percent="percent"
          size="small"
          :show-info="false"
          stroke-color="var(--color-accent)"
          trail-color="var(--color-accent-soft)"
        />
        <span class="evidence-card__confidence-value mono">{{ percent }}%</span>
      </div>

      <a-tag class="evidence-card__prompt-tag mono">
        {{ evidence.prompt_key }} v{{ evidence.prompt_version }}
      </a-tag>

      <RouterLink
        class="evidence-card__run-link mono"
        :to="{ path: '/ops', query: { run_id: evidence.run_id } }"
        title="跳转到流水线面板查看这次抽取"
      >
        run·{{ runIdShort }}
      </RouterLink>
    </div>
  </article>
</template>

<style scoped lang="scss">
.evidence-card {
  background: var(--color-accent-soft);
  border-left: 3px solid var(--color-accent);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.evidence-card__snippet {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text);
  white-space: pre-wrap;
}

.evidence-card__source {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  font-size: 12.5px;
}

.evidence-card__source-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-accent-strong);
  font-weight: 600;
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.evidence-card__external-icon {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
}

.evidence-card__dot {
  color: var(--color-text-muted);
}

.evidence-card__meta {
  color: var(--color-text-muted);
}

.evidence-card__footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-4);
  padding-top: var(--space-2);
  border-top: 1px solid rgba(181, 101, 29, 0.18);
}

.evidence-card__confidence {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 120px;
}

.evidence-card__progress {
  width: 72px;
  line-height: 0;
}

.evidence-card__confidence-value {
  font-size: 12px;
  color: var(--color-accent-strong);
}

.evidence-card__prompt-tag {
  font-size: 11px;
}

.evidence-card__run-link {
  font-size: 12px;
  color: var(--color-text-muted);
  text-decoration: none;
  margin-left: auto;

  &:hover {
    color: var(--color-accent-strong);
    text-decoration: underline;
  }
}
</style>
