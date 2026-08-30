<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

interface NavItem {
  key: string
  label: string
  to: string
  index: string
}

const NAV_ITEMS: NavItem[] = [
  { key: 'brief', label: '今日简报', to: '/', index: '01' },
  { key: 'wiki', label: '词条库', to: '/wiki', index: '02' },
  { key: 'graph', label: '关系图谱', to: '/graph', index: '03' },
  { key: 'ops', label: '流水线', to: '/ops', index: '04' },
]

const route = useRoute()
const activeKey = computed(() => route.meta.navKey)
</script>

<template>
  <aside class="app-sider">
    <div class="app-sider__brand">
      <RouterLink to="/" class="app-sider__wordmark">
        news<span class="app-sider__dot">·</span>wiki
      </RouterLink>
      <p class="app-sider__tagline">可溯源的 AI 资讯维基</p>
    </div>

    <nav class="app-sider__nav">
      <RouterLink
        v-for="item in NAV_ITEMS"
        :key="item.key"
        :to="item.to"
        class="app-sider__link"
        :class="{ 'app-sider__link--active': activeKey === item.key }"
      >
        <span class="app-sider__index mono">{{ item.index }}</span>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="app-sider__footer mono">v0.1 · demo</div>
  </aside>
</template>

<style scoped lang="scss">
.app-sider {
  width: var(--sider-width);
  min-width: var(--sider-width);
  height: 100%;
  background: var(--color-sider-bg);
  color: var(--color-sider-text);
  display: flex;
  flex-direction: column;
  padding: var(--space-5) 0 0;
}

.app-sider__brand {
  padding: 0 var(--space-5) var(--space-5);
  border-bottom: 1px solid var(--color-sider-border);
  margin-bottom: var(--space-4);
}

.app-sider__wordmark {
  display: inline-block;
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 600;
  color: var(--color-text-on-dark);
  text-decoration: none;
  letter-spacing: -0.01em;
}

.app-sider__dot {
  color: var(--color-accent);
}

.app-sider__tagline {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  color: var(--color-sider-text-muted);
}

.app-sider__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 var(--space-3);
  flex: 1;
}

.app-sider__link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  color: var(--color-sider-text-muted);
  text-decoration: none;
  font-size: 14px;
  transition:
    background var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.app-sider__link:hover {
  background: var(--color-sider-bg-raised);
  color: var(--color-text-on-dark);
}

.app-sider__index {
  font-size: 11px;
  color: var(--color-accent);
  opacity: 0.85;
}

.app-sider__link--active {
  background: var(--color-sider-bg-raised);
  color: var(--color-text-on-dark);
  box-shadow: inset 3px 0 0 var(--color-accent);
}

.app-sider__footer {
  padding: var(--space-4) var(--space-5);
  font-size: 11px;
  color: var(--color-sider-text-muted);
  border-top: 1px solid var(--color-sider-border);
  margin-top: var(--space-4);
}
</style>
