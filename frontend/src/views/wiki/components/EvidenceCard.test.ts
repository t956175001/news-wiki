import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import EvidenceCard from './EvidenceCard.vue'
import type { Evidence } from '@/types/wiki'

const evidence: Evidence = {
  id: 301,
  snippet: 'OpenAI 于本周正式发布 GPT-5，主打推理能力提升。',
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
}

async function mountCard(confidence = 0.92) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [{ path: '/ops', name: 'ops', component: { template: '<div />' } }],
  })
  router.push('/')
  await router.isReady()
  const wrapper = mount(EvidenceCard, {
    props: { evidence, confidence },
    global: { plugins: [router, Antd] },
  })
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('EvidenceCard', () => {
  it('renders the original snippet as quoted evidence', async () => {
    const wrapper = await mountCard()
    expect(wrapper.text()).toContain(evidence.snippet)
  })

  it('renders the source article as an external link with title, source name and time', async () => {
    const wrapper = await mountCard()
    const link = wrapper.find(`a[href="${evidence.article.url}"]`)
    expect(link.exists()).toBe(true)
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
    expect(link.text()).toContain(evidence.article.title)
    expect(wrapper.text()).toContain(evidence.article.source_name)
    expect(wrapper.text()).toContain('2026-08-27')
  })

  it('renders confidence as a progress bar with a numeric percentage', async () => {
    const wrapper = await mountCard(0.92)
    expect(wrapper.text()).toContain('92%')
    expect(wrapper.find('.ant-progress').exists()).toBe(true)
  })

  it('renders the prompt key and version as a tag', async () => {
    const wrapper = await mountCard()
    expect(wrapper.text()).toContain('wiki.extract_linkages')
    expect(wrapper.text()).toContain('v2')
  })

  it('renders a truncated run_id linking to the ops panel with the full id', async () => {
    const wrapper = await mountCard()
    const truncated = evidence.run_id.slice(0, 8)
    const runLink = wrapper.findAll('a').find((a) => a.attributes('href')?.startsWith('/ops'))
    expect(runLink).toBeTruthy()
    expect(runLink!.text()).toContain(truncated)
    expect(runLink!.attributes('href')).toContain(evidence.run_id)
  })

  it('handles a missing source_name gracefully', async () => {
    const noSource: Evidence = {
      ...evidence,
      article: { ...evidence.article, source_name: null },
    }
    const router = createRouter({
      history: createWebHistory(),
      routes: [{ path: '/ops', component: { template: '<div />' } }],
    })
    router.push('/')
    await router.isReady()
    const wrapper = mount(EvidenceCard, {
      props: { evidence: noSource, confidence: 0.5 },
      global: { plugins: [router, Antd] },
    })
    expect(wrapper.text()).toContain(noSource.article.title)
  })
})
