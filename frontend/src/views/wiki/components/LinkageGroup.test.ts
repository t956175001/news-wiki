import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import LinkageGroup from './LinkageGroup.vue'
import type { LinkageWithEvidence } from '@/types/wiki'

const linkages: LinkageWithEvidence[] = [
  {
    id: 88,
    direction: 'out',
    predicate: '发布',
    object: { kind: 'entity', id: 45, name: 'GPT-5', entity_type: 'product' },
    confidence: 0.92,
    evidences: [
      {
        id: 301,
        snippet: 'OpenAI 于本周正式发布 GPT-5。',
        prompt_key: 'wiki.extract_linkages',
        prompt_version: 2,
        run_id: 'a3f9c1e2b4d5f6a7b8c9d0e1f2a3b4c5',
        article: {
          id: 42,
          title: 'OpenAI 发布 GPT-5',
          url: 'https://example.com/gpt5',
          publish_time: '2026-08-27T10:00:00Z',
          source_name: '机器之心',
        },
      },
    ],
  },
  {
    id: 89,
    direction: 'in',
    predicate: '发布',
    object: { kind: 'entity', id: 7, name: 'Sam Altman', entity_type: 'person' },
    confidence: 0.81,
    evidences: [],
  },
  {
    id: 90,
    direction: 'out',
    predicate: '采用',
    object: { kind: 'concept', id: 3, name: '混合专家模型', namespace: 'technique' },
    confidence: 0.75,
    evidences: [],
  },
]

async function mountGroup(props: { linkages: LinkageWithEvidence[] }) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [{ path: '/wiki/:id', component: { template: '<div />' } }],
  })
  router.push('/')
  await router.isReady()
  const wrapper = mount(LinkageGroup, { props, global: { plugins: [router, Antd] } })
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('LinkageGroup', () => {
  it('groups a flat linkage list into sections keyed by predicate', async () => {
    const wrapper = await mountGroup({ linkages })
    const sections = wrapper.findAll('.linkage-group__section')
    expect(sections).toHaveLength(2)

    expect(sections[0].find('.linkage-group__predicate').text()).toContain('发布')
    expect(sections[0].findAll('.linkage-row')).toHaveLength(2)

    expect(sections[1].find('.linkage-group__predicate').text()).toContain('采用')
    expect(sections[1].findAll('.linkage-row')).toHaveLength(1)
  })

  it('renders the object name, direction and confidence for each relation', async () => {
    const wrapper = await mountGroup({ linkages })
    const text = wrapper.text()
    expect(text).toContain('GPT-5')
    expect(text).toContain('Sam Altman')
    expect(text).toContain('混合专家模型')
    expect(text).toContain('92%')
    expect(text).toContain('81%')
    expect(text).toContain('75%')
  })

  it('links entity objects to their entry page but leaves concept objects unlinked', async () => {
    const wrapper = await mountGroup({ linkages })
    expect(wrapper.find('a[href="/wiki/45"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/wiki/7"]').exists()).toBe(true)
    expect(wrapper.find('a[href="/wiki/3"]').exists()).toBe(false)
  })

  it('distinguishes outgoing and incoming relations', async () => {
    const wrapper = await mountGroup({ linkages })
    const directions = wrapper.findAll('.linkage-row__direction')
    expect(directions[0].attributes('aria-label')).toBe('流出关系')
    expect(directions[1].attributes('aria-label')).toBe('流入关系')
  })

  it('expands a relation to reveal its evidence, and collapses again', async () => {
    const wrapper = await mountGroup({ linkages })
    expect(wrapper.text()).not.toContain('OpenAI 于本周正式发布 GPT-5。')

    const toggle = wrapper.find('.linkage-row .linkage-row__toggle')
    await toggle.trigger('click')
    expect(wrapper.text()).toContain('OpenAI 于本周正式发布 GPT-5。')

    await toggle.trigger('click')
    expect(wrapper.text()).not.toContain('OpenAI 于本周正式发布 GPT-5。')
  })

  it('shows a fallback message when an expanded relation has no evidence', async () => {
    const wrapper = await mountGroup({ linkages: [linkages[1]] })
    const toggle = wrapper.find('.linkage-row__toggle')
    await toggle.trigger('click')
    expect(wrapper.text()).toContain('暂无原文证据')
  })
})
