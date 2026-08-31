import { createRouter, createWebHistory } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    navKey?: string
    /** Appended before the site name in document.title. */
    title?: string
  }
}

const SITE_NAME = 'news-wiki'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'brief',
      component: () => import('@/views/brief/BriefView.vue'),
      meta: { navKey: 'brief', title: '今日简报' },
    },
    {
      path: '/wiki',
      name: 'entity-list',
      component: () => import('@/views/wiki/EntityListView.vue'),
      meta: { navKey: 'wiki', title: '词条库' },
    },
    {
      path: '/wiki/:id',
      name: 'entity-detail',
      component: () => import('@/views/wiki/EntityDetailView.vue'),
      props: true,
      meta: { navKey: 'wiki', title: '词条详情' },
    },
    {
      path: '/graph',
      name: 'graph',
      component: () => import('@/views/wiki/GraphView.vue'),
      meta: { navKey: 'graph', title: '关系图谱' },
    },
    {
      path: '/ops',
      name: 'ops',
      component: () => import('@/views/ops/OpsView.vue'),
      meta: { navKey: 'ops', title: '流水线面板' },
    },
  ],

  // Only the anchor case lives here. `savedPosition` and `{ top: 0 }` both act
  // on the window, and this layout does not scroll the window — the scroll
  // container is `.app-shell__content` inside DefaultLayout, which owns its own
  // save/restore. `scrollIntoView` (what returning `el` does) is the exception:
  // it walks every scrollable ancestor, so it finds the right one by itself.
  scrollBehavior(to) {
    // The brief's [n] citation markers are in-page anchors; this is the jump
    // to the matching reference at the bottom of the page.
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return false
  },
})

// Five pages sharing one title makes browser history and a row of tabs useless.
router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · ${SITE_NAME}` : SITE_NAME
})

export default router
