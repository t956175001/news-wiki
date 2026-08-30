<script setup lang="ts">
withDefaults(defineProps<{ tip?: string }>(), { tip: '加载中…' })
</script>

<template>
  <div class="loading-panel">
    <a-spin size="large" />
    <p class="loading-panel__tip">{{ tip }}</p>
  </div>
</template>

<style scoped lang="scss">
.loading-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-8);
}

.loading-panel__tip {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
