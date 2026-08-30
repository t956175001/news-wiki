import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RunDetail from './RunDetail.vue'
import type { StepMetrics } from '@/types/ops'

const stepMetrics: StepMetrics = {
  ingest: { status: 'done', elapsed_ms: 4210, fetched: 12, deduped: 3, saved: 9 },
  extract_entities: {
    status: 'done',
    elapsed_ms: 8300,
    prompt_tokens: 5120,
    completion_tokens: 890,
    count: 24,
    attempts: 1,
  },
  extract_concepts: {
    status: 'failed',
    elapsed_ms: 6100,
    error_message: 'JSON 解析失败：unexpected token',
    attempts: 3,
  },
  // extract_linkages, persist, brief never ran — the pipeline stopped at extract_concepts.
}

describe('RunDetail', () => {
  it('renders all six fixed pipeline steps in order', () => {
    const wrapper = mount(RunDetail, { props: { stepMetrics } })
    const steps = wrapper.findAll('.run-detail__step')
    expect(steps).toHaveLength(6)
  })

  it('renders the error message for a failed step', () => {
    const wrapper = mount(RunDetail, { props: { stepMetrics } })
    expect(wrapper.text()).toContain('JSON 解析失败：unexpected token')
  })

  it('greys out steps that were never executed', () => {
    const wrapper = mount(RunDetail, { props: { stepMetrics } })
    const pendingSteps = wrapper.findAll('.run-detail__step--pending')
    const pendingText = pendingSteps.map((el) => el.text())

    expect(pendingSteps).toHaveLength(3)
    expect(pendingText.some((text) => text.includes('抽取关系'))).toBe(true)
    expect(pendingText.some((text) => text.includes('落库'))).toBe(true)
    expect(pendingText.some((text) => text.includes('生成简报'))).toBe(true)
  })

  it('shows elapsed time, token count and attempts for a completed step', () => {
    const wrapper = mount(RunDetail, { props: { stepMetrics } })
    expect(wrapper.text()).toContain('8300ms')
    expect(wrapper.text()).toContain('6010 tokens')
    expect(wrapper.text()).toContain('尝试 1 次')
  })

  it('marks a failed step distinctly from a done step', () => {
    const wrapper = mount(RunDetail, { props: { stepMetrics } })
    expect(wrapper.findAll('.run-detail__step--failed')).toHaveLength(1)
  })
})
