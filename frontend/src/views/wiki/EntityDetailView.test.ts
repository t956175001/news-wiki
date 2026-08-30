import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import EntityDetailView from './EntityDetailView.vue'
import { ApiError } from '@/api/client'
import type { EntityDetail } from '@/types/wiki'

vi.mock('@/api/wiki', () => ({
  getEntity: vi.fn(),
}))

import { getEntity } from '@/api/wiki'

const mockedGetEntity = vi.mocked(getEntity)

function baseEntity(overrides: Partial<EntityDetail> = {}): EntityDetail {
  return {
    id: 12,
    name: 'OpenAI',
    entity_type: 'org',
    entity_type_display: 'Organization',
    aliases: ['Open AI'],
    summary: '美国人工智能研究公司。',
    confidence: 0.95,
    mention_count: 17,
    first_seen_at: '2026-08-01T08:00:00Z',
    last_seen_at: '2026-08-27T09:30:00Z',
    linkages: [],
    ...overrides,
  }
}

async function mountAt(id: string | number) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/wiki', component: { template: '<div />' } },
      { path: '/wiki/:id', component: EntityDetailView },
      { path: '/ops', component: { template: '<div />' } },
    ],
  })
  router.push(`/wiki/${id}`)
  await router.isReady()
  const wrapper = mount(EntityDetailView, { global: { plugins: [router, Antd] } })
  return { wrapper, router }
}

describe('EntityDetailView', () => {
  beforeEach(() => {
    mockedGetEntity.mockReset()
  })

  it('shows a skeleton before the request resolves', async () => {
    mockedGetEntity.mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountAt(12)
    expect(wrapper.find('.ant-skeleton').exists()).toBe(true)
  })

  it('renders the header and grouped relations once loaded', async () => {
    mockedGetEntity.mockResolvedValue(
      baseEntity({
        linkages: [
          {
            id: 88,
            direction: 'out',
            predicate: '发布',
            object: { kind: 'entity', id: 45, name: 'GPT-5', entity_type: 'product' },
            confidence: 0.92,
            evidences: [],
          },
        ],
      }),
    )
    const { wrapper } = await mountAt(12)
    await flushPromises()

    expect(mockedGetEntity).toHaveBeenCalledWith(12)
    expect(wrapper.find('.ant-skeleton').exists()).toBe(false)
    expect(wrapper.text()).toContain('OpenAI')
    expect(wrapper.text()).toContain('Open AI')
    expect(wrapper.text()).toContain('美国人工智能研究公司。')
    expect(wrapper.text()).toContain('17')
    expect(wrapper.text()).toContain('发布')
    expect(wrapper.text()).toContain('GPT-5')
  })

  it('shows an empty state when the entity has no relations', async () => {
    mockedGetEntity.mockResolvedValue(baseEntity({ linkages: [] }))
    const { wrapper } = await mountAt(12)
    await flushPromises()
    expect(wrapper.text()).toContain('该实体暂未抽取到关联关系')
  })

  it('shows a not-found state with a link back to the list on 404', async () => {
    mockedGetEntity.mockRejectedValue(new ApiError('not_found', 'Not found.'))
    const { wrapper } = await mountAt(999)
    await flushPromises()
    expect(wrapper.text()).toContain('该实体不存在')
    expect(wrapper.find('a[href="/wiki"]').exists()).toBe(true)
  })

  it('shows a retryable error state on other failures', async () => {
    mockedGetEntity.mockRejectedValue(new ApiError('NETWORK_ERROR', '网络错误，请稍后重试'))
    const { wrapper } = await mountAt(12)
    await flushPromises()
    expect(wrapper.text()).toContain('网络错误，请稍后重试')
  })
})
