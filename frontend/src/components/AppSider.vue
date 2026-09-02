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
  { key: 'ops', label: '工作流', to: '/ops', index: '04' },
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

    <div class="app-sider__footer mono">
      <span class="app-sider__version">v0.1 · demo</span>
      <span class="app-sider__links">
        <a
          class="app-sider__external app-sider__profile"
          href="https://github.com/t956175001"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Junhe Tang 的 GitHub 主页"
        >
          <!-- Inlined rather than fetched: the Caddy CSP is `default-src 'self'`,
               and a third-party origin on first paint is the exact shape of the
               font bug that left mainland visitors staring at a blank page. -->
          <svg
            class="app-sider__gh"
            viewBox="0 0 16 16"
            width="13"
            height="13"
            aria-hidden="true"
            focusable="false"
          >
            <path
              fill="currentColor"
              d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27s-1.36.09-2 .27c-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z"
            />
          </svg>
          <span class="app-sider__author">Junhe Tang</span>
        </a>
        <span class="app-sider__sep" aria-hidden="true">·</span>
        <a
          class="app-sider__external app-sider__source"
          href="https://github.com/t956175001/news-wiki"
          target="_blank"
          rel="noopener noreferrer"
          >源码</a
        >
      </span>
    </div>
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
  display: flex;
  flex-direction: column;
  gap: var(--space-2);

  // The collapsed top bar keeps only the mark. Measured at 375px: the full
  // `Junhe Tang · 源码` leaves the nav about 120px, which truncates the first
  // item and pushes the other three into a scroll nobody will discover.
  @media (max-width: 768px) {
    flex-direction: row;
    align-items: center;
    margin-top: 0;
    margin-left: auto;
    padding: 0 var(--space-1) 0 var(--space-3);
    border-top: none;
    border-left: 1px solid var(--color-sider-border);
    flex-shrink: 0;
    align-self: stretch;
  }
}

.app-sider__profile {
  display: flex;
  align-items: center;
  gap: var(--space-2);

  @media (max-width: 768px) {
    // The mark alone is 16px; pad the hit area out to the WCAG 2.2 minimum.
    min-width: 24px;
    min-height: 24px;
    justify-content: center;
  }
}

// Hidden rather than dropped from the DOM so the desktop layout stays the
// single source of truth for what the footer says.
.app-sider__version,
.app-sider__author,
.app-sider__sep,
.app-sider__source {
  @media (max-width: 768px) {
    display: none;
  }
}

.app-sider__links {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  white-space: nowrap;
}

.app-sider__gh {
  flex-shrink: 0;
  opacity: 0.75;

  @media (max-width: 768px) {
    width: 16px;
    height: 16px;
  }
}

.app-sider__external {
  color: var(--color-sider-text-muted);
  text-decoration: none;
  transition: color var(--duration-fast) var(--ease-standard);
}

.app-sider__external:hover {
  color: var(--color-accent);
  text-decoration: underline;
}
</style>
