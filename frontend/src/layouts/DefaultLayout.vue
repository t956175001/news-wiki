<script setup lang="ts">
import { ref } from 'vue'
import AppSider from '@/components/AppSider.vue'
import AppHeader from '@/components/AppHeader.vue'
import { useScrollRestoration } from '@/composables/useScrollRestoration'

// This element, not the window, is what scrolls — see the composable.
const content = ref<HTMLElement | null>(null)
useScrollRestoration(content)
</script>

<template>
  <div class="app-shell">
    <AppSider />
    <div class="app-shell__body">
      <AppHeader />
      <main ref="content" class="app-shell__content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped lang="scss">
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;

  @media (max-width: 768px) {
    flex-direction: column;
  }
}

.app-shell__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  // `min-width: 0` lets this shrink on the row layout's main axis (desktop).
  // `min-height: 0` is its column-layout (mobile) counterpart: without it, a
  // flex item's height still defaults to its content's natural size, so this
  // grows past the 100vh shell instead of deferring to `.app-shell__content`'s
  // own scroll — the shell's `overflow: hidden` then just clips everything
  // below the fold, unreachable, rather than the page scrolling to it.
  min-width: 0;
  min-height: 0;
}

.app-shell__content {
  flex: 1;
  overflow-y: auto;
  background: var(--color-content-bg);
}
</style>
