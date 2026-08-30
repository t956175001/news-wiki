import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import type { GraphData } from '@/types/wiki'

const mockChart = {
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  on: vi.fn(),
}

vi.mock('echarts', () => ({
  init: vi.fn(() => mockChart),
}))

import * as echarts from 'echarts'
import GraphChart from './GraphChart.vue'

const sampleData: GraphData = {
  nodes: [
    { id: 'e12', name: 'OpenAI', category: 'org', value: 3, symbolSize: 18 },
    { id: 'c3', name: '混合专家模型', category: 'technique', value: 1, symbolSize: 14 },
  ],
  links: [{ source: 'e12', target: 'c3', predicate: '采用', value: 0.7 }],
  categories: [{ name: 'org' }, { name: 'technique' }],
  truncated: false,
}

describe('GraphChart', () => {
  let wrapper: VueWrapper | undefined

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
  })

  it('initializes echarts and passes the graph data through untransformed', () => {
    wrapper = mount(GraphChart, { props: { data: sampleData } })

    expect(echarts.init).toHaveBeenCalledTimes(1)
    expect(mockChart.setOption).toHaveBeenCalledTimes(1)
    const option = mockChart.setOption.mock.calls[0][0]
    const series = option.series[0]
    expect(series.type).toBe('graph')
    expect(series.data).toEqual(sampleData.nodes)
    expect(series.links).toEqual(sampleData.links)
    expect(series.categories).toEqual(sampleData.categories)
  })

  it('resizes the chart when the window resizes', () => {
    wrapper = mount(GraphChart, { props: { data: sampleData } })
    window.dispatchEvent(new Event('resize'))
    expect(mockChart.resize).toHaveBeenCalledTimes(1)
  })

  it('disposes the chart instance on unmount', () => {
    wrapper = mount(GraphChart, { props: { data: sampleData } })
    wrapper.unmount()
    wrapper = undefined
    expect(mockChart.dispose).toHaveBeenCalledTimes(1)
  })

  it('emits nodeClick with the raw prefixed id when a node is clicked', () => {
    wrapper = mount(GraphChart, { props: { data: sampleData } })
    const clickHandler = mockChart.on.mock.calls.find(([event]) => event === 'click')?.[1]
    clickHandler?.({ dataType: 'node', data: { id: 'e12' } })
    expect(wrapper.emitted('nodeClick')).toEqual([['e12']])
  })

  it('re-renders with new data without re-initializing the chart', async () => {
    wrapper = mount(GraphChart, { props: { data: sampleData } })
    const nextData: GraphData = { ...sampleData, truncated: true }
    await wrapper.setProps({ data: nextData })

    expect(echarts.init).toHaveBeenCalledTimes(1)
    expect(mockChart.setOption).toHaveBeenCalledTimes(2)
  })
})
