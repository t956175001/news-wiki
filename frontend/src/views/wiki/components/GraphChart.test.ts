import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import type { GraphData } from '@/types/wiki'

const mockChart = {
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  on: vi.fn(),
}

vi.mock('echarts/core', () => ({
  init: vi.fn(() => mockChart),
  use: vi.fn(),
}))
vi.mock('echarts/charts', () => ({ GraphChart: {} }))
vi.mock('echarts/components', () => ({ TooltipComponent: {}, LegendComponent: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

import * as echarts from 'echarts/core'
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
    expect(series.links).toEqual(sampleData.links)
    expect(series.categories).toEqual(sampleData.categories)
    // Nodes pass through as the backend shaped them; the only thing added is
    // the per-node label visibility decided below.
    const withoutLabel = series.data.map((node: Record<string, unknown>) => {
      const copy = { ...node }
      delete copy.label
      return copy
    })
    expect(withoutLabel).toEqual(sampleData.nodes)
  })

  it('escapes HTML in tooltips, which echarts renders unescaped', () => {
    // Node names are LLM output derived from scraped pages. A name carrying a
    // tag is the one path from an article we do not control to script in the
    // page, so it has to come back inert.
    const hostile: GraphData = {
      ...sampleData,
      nodes: [
        {
          id: 'e1',
          name: '<img src=x onerror=alert(1)>',
          category: 'org',
          value: 2,
          symbolSize: 16,
        },
      ],
      links: [{ source: 'e1', target: 'e1', predicate: '<script>alert(2)</script>', value: 0.5 }],
    }
    wrapper = mount(GraphChart, { props: { data: hostile } })
    const { formatter } = mockChart.setOption.mock.calls[0][0].tooltip

    const nodeHtml = formatter({ dataType: 'node', data: hostile.nodes[0] })
    const edgeHtml = formatter({ dataType: 'edge', data: hostile.links[0] })

    expect(nodeHtml).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(nodeHtml).not.toContain('<img')
    expect(edgeHtml).toBe('&lt;script&gt;alert(2)&lt;/script&gt;')
  })

  it('labels only well-connected nodes once the graph gets crowded', () => {
    // 150 labels at once is a wall of text; the rest surface on hover via
    // emphasis.label, which is asserted here too so it is not silently lost.
    const crowded: GraphData = {
      ...sampleData,
      nodes: Array.from({ length: 50 }, (_, index) => ({
        id: `e${index}`,
        name: `n${index}`,
        category: 'org',
        value: index < 5 ? 4 : 1,
        symbolSize: 14,
      })),
    }
    wrapper = mount(GraphChart, { props: { data: crowded } })
    const series = mockChart.setOption.mock.calls[0][0].series[0]

    expect(
      series.data.filter((node: { label: { show: boolean } }) => node.label.show),
    ).toHaveLength(5)
    expect(series.emphasis.label.show).toBe(true)
  })

  it('labels everything while the graph is still small', () => {
    wrapper = mount(GraphChart, { props: { data: sampleData } })
    const series = mockChart.setOption.mock.calls[0][0].series[0]

    expect(series.data.every((node: { label: { show: boolean } }) => node.label.show)).toBe(true)
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
