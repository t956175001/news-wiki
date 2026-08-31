<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{ fallback: string; label?: string }>(), {
  label: '返回',
})

const router = useRouter()

/**
 * Prefer real history over a fixed destination.
 *
 * `router.back()` alone is wrong when this page was opened directly — a shared
 * link, a new tab — because there is nothing to go back to and the button does
 * nothing. `history.state.back` is how vue-router records whether it put an
 * entry behind this one, so it answers exactly that question.
 *
 * Going back rather than pushing the fallback matters here: the entry list
 * keeps its filters in the URL, so the previous history entry is the list the
 * visitor actually had, not a freshly reset one.
 */
function goBack() {
  if (window.history.state?.back) {
    router.back()
  } else {
    router.push(props.fallback)
  }
}
</script>

<template>
  <button type="button" class="page-back" @click="goBack">
    <span aria-hidden="true">←</span>
    <span>{{ label }}</span>
  </button>
</template>

<style scoped lang="scss">
.page-back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3) var(--space-1) var(--space-2);
  margin-left: calc(var(--space-2) * -1);
  border: none;
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);

  &:hover {
    background: var(--color-surface-sunken);
    color: var(--color-text);
  }
}
</style>
