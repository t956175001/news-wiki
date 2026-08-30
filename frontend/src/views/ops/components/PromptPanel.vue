<script setup lang="ts">
import { reactive } from 'vue'
import dayjs from 'dayjs'
import type { PromptTemplate } from '@/types/prompts'

defineProps<{ prompts: PromptTemplate[] }>()

const expandedKeys = reactive(new Set<string>())

function toggle(key: string) {
  if (expandedKeys.has(key)) {
    expandedKeys.delete(key)
  } else {
    expandedKeys.add(key)
  }
}

function formatDate(value: string) {
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}
</script>

<template>
  <section class="prompt-panel">
    <div class="prompt-panel__header">
      <h2 class="prompt-panel__title">Prompt 版本</h2>
      <span class="prompt-panel__readonly-tag">只读展示 · 无编辑入口</span>
    </div>

    <ul class="prompt-panel__list">
      <li v-for="prompt in prompts" :key="prompt.key" class="prompt-panel__item">
        <button
          type="button"
          class="prompt-panel__row"
          :aria-expanded="expandedKeys.has(prompt.key)"
          @click="toggle(prompt.key)"
        >
          <span class="prompt-panel__key mono">{{ prompt.key }}</span>
          <span class="prompt-panel__name">{{ prompt.name }}</span>
          <span class="prompt-panel__version mono"
            >v{{ prompt.current_version?.version_no ?? '—' }}</span
          >
          <span class="prompt-panel__updated mono">{{
            formatDate(prompt.current_version?.created_at ?? prompt.created_at)
          }}</span>
          <span class="prompt-panel__chevron" aria-hidden="true">{{
            expandedKeys.has(prompt.key) ? '收起 −' : '展开 +'
          }}</span>
        </button>

        <pre v-if="expandedKeys.has(prompt.key)" class="prompt-panel__text mono">{{
          prompt.current_version?.text ?? prompt.default_text
        }}</pre>
      </li>
    </ul>
  </section>
</template>

<style scoped lang="scss">
.prompt-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.prompt-panel__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.prompt-panel__title {
  font-size: 16px;
}

.prompt-panel__readonly-tag {
  font-size: 11px;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  padding: 2px var(--space-3);
}

.prompt-panel__list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--color-border);
}

.prompt-panel__item {
  border-bottom: 1px solid var(--color-border);
}

.prompt-panel__row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-1);
  background: none;
  border: none;
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: left;

  &:hover {
    color: var(--color-accent-strong);
  }
}

.prompt-panel__key {
  font-size: 12px;
  color: var(--color-text-muted);
  flex-shrink: 0;
  width: 180px;
}

.prompt-panel__name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
}

.prompt-panel__version {
  font-size: 12px;
  color: var(--color-accent-strong);
}

.prompt-panel__updated {
  font-size: 12px;
  color: var(--color-text-muted);
}

.prompt-panel__chevron {
  font-size: 12px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.prompt-panel__text {
  margin: 0 0 var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-sunken);
  border-radius: var(--radius-md);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}
</style>
