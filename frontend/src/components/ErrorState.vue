<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string
    code?: string
  }>(),
  {
    message: '加载失败，请稍后重试。',
    code: '',
  },
)

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="error-state">
    <p class="error-state__message">{{ message }}</p>
    <p v-if="code" class="error-state__code mono">{{ code }}</p>
    <a-button size="small" @click="emit('retry')">重试</a-button>
  </div>
</template>

<style scoped lang="scss">
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-5);
  text-align: center;
}

.error-state__message {
  margin: 0;
  font-size: 14px;
  color: var(--color-danger);
}

.error-state__code {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
