<script setup lang="ts">
import AppSider from '@/components/AppSider.vue'
import AppHeader from '@/components/AppHeader.vue'
</script>

<template>
  <div class="app-shell">
    <AppSider />
    <div class="app-shell__body">
      <AppHeader />
      <main class="app-shell__content">
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
}

.app-shell__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.app-shell__content {
  flex: 1;
  overflow-y: auto;
  background: var(--color-content-bg);
}
</style>
