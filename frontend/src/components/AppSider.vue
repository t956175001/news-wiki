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

  // Below this width the fixed 232px sider would eat most of the viewport
  // and squeeze content into an unreadably narrow column, so it collapses
  // into a fixed-height horizontal top bar instead of an off-canvas drawer —
  // simplest fix that satisfies "no horizontal scroll on the page itself".
  // The bar itself has a fixed height rather than `height: auto`: making a
  // flex row BOTH auto-height and a scroll container (overflow-x: auto forces
  // overflow-y to compute as auto too) collapses its auto height to just the
  // padding, because the "hypothetical cross size" it'd auto-size to no
  // longer accounts for the now-scrollable children. Only `.app-sider__nav`
  // itself scrolls horizontally; the bar's own height stays predictable.
  @media (max-width: 768px) {
    width: 100%;
    min-width: 0;
    height: 56px;
    flex-direction: row;
    align-items: center;
    padding: 0 var(--space-3);
  }
}

.app-sider__brand {
  padding: 0 var(--space-5) var(--space-5);
  border-bottom: 1px solid var(--color-sider-border);
  margin-bottom: var(--space-4);

  @media (max-width: 768px) {
    padding: 0 var(--space-3) 0 0;
    border-bottom: none;
    border-right: 1px solid var(--color-sider-border);
    margin-bottom: 0;
    flex-shrink: 0;
  }
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

  @media (max-width: 768px) {
    display: none;
  }
}

.app-sider__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 var(--space-3);
  flex: 1;

  @media (max-width: 768px) {
    flex-direction: row;
    flex: initial;
    padding: 0 0 0 var(--space-3);
    gap: var(--space-1);
    height: 100%;
    align-items: center;
    overflow-x: auto;
  }
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

  @media (max-width: 768px) {
    padding: var(--space-2) var(--space-3);
    white-space: nowrap;
    flex-shrink: 0;
  }
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

  @media (max-width: 768px) {
    box-shadow: inset 0 -3px 0 var(--color-accent);
  }
}

.app-sider__footer {
  padding: var(--space-4) var(--space-5);
  font-size: 11px;
  color: var(--color-sider-text-muted);
  border-top: 1px solid var(--color-sider-border);
  margin-top: var(--space-4);

  @media (max-width: 768px) {
    display: none;
  }
}
</style>
