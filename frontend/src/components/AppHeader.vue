<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'

const TITLES: Record<string, string> = {
  brief: '今日简报',
  wiki: '词条库',
  graph: '关系图谱',
  ops: '流水线面板',
}

const route = useRoute()
const title = computed(() => TITLES[route.meta.navKey ?? ''] ?? 'news-wiki')
const today = dayjs().format('YYYY年M月D日')
</script>

<template>
  <header class="app-header">
    <h2 class="app-header__title">{{ title }}</h2>
    <div class="app-header__meta mono">{{ today }}</div>
  </header>
</template>

<style scoped lang="scss">
.app-header {
  height: var(--header-height);
  min-height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  gap: var(--space-3);

  @media (max-width: 768px) {
    padding: 0 var(--space-4);
  }
}

.app-header__title {
  font-size: 18px;
}

.app-header__meta {
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
