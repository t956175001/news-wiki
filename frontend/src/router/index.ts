import { createRouter, createWebHistory } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    navKey?: string
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'brief',
      component: () => import('@/views/brief/BriefView.vue'),
      meta: { navKey: 'brief' },
    },
    {
      path: '/wiki',
      name: 'entity-list',
      component: () => import('@/views/wiki/EntityListView.vue'),
      meta: { navKey: 'wiki' },
    },
    {
      path: '/wiki/:id',
      name: 'entity-detail',
      component: () => import('@/views/wiki/EntityDetailView.vue'),
      props: true,
      meta: { navKey: 'wiki' },
    },
    {
      path: '/graph',
      name: 'graph',
      component: () => import('@/views/wiki/GraphView.vue'),
      meta: { navKey: 'graph' },
    },
    {
      path: '/ops',
      name: 'ops',
      component: () => import('@/views/ops/OpsView.vue'),
      meta: { navKey: 'ops' },
    },
  ],
})

export default router
