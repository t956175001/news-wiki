<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    description?: string
  }>(),
  {
    title: '暂无数据',
    description: '',
  },
)
</script>

<template>
  <div class="empty-state">
    <div class="empty-state__mark" aria-hidden="true">·</div>
    <p class="empty-state__title">{{ title }}</p>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <slot />
  </div>
</template>

<style scoped lang="scss">
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-5);
  color: var(--color-text-muted);
  text-align: center;
}

.empty-state__mark {
  font-family: var(--font-display);
  font-size: 40px;
  color: var(--color-accent);
  line-height: 1;
  margin-bottom: var(--space-3);
}

.empty-state__title {
  font-size: 15px;
  color: var(--color-text);
  margin: 0 0 var(--space-1);
}

.empty-state__desc {
  font-size: 13px;
  margin: 0;
}
</style>
