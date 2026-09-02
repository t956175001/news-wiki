import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import type { GraphData } from '@/types/wiki'

const mockChart = {
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  on: vi.fn(),
  getZr: vi.fn(() => ({ on: vi.fn() })),
}
vi.mock('echarts/core', () => ({ init: vi.fn(() => mockChart), use: vi.fn() }))
vi.mock('echarts/charts', () => ({ GraphChart: {} }))
vi.mock('echarts/components', () => ({ TooltipComponent: {}, LegendComponent: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

vi.mock('@/api/wiki', () => ({
  getGraph: vi.fn(),
  getEntity: vi.fn(),
  getConcept: vi.fn(),
}))

import { getGraph, getEntity, getConcept } from '@/api/wiki'
import GraphView from './GraphView.vue'
import GraphChart from './components/GraphChart.vue'

const mockedGetGraph = vi.mocked(getGraph)
const mockedGetEntity = vi.mocked(getEntity)
const mockedGetConcept = vi.mocked(getConcept)

const sample: GraphData = {
  nodes: [
    { id: 'e12', name: 'OpenAI', category: 'org', value: 3, symbolSize: 18 },
    { id: 'e45', name: 'GPT-5', category: 'product', value: 2, symbolSize: 16 },
    { id: 'c3', name: '混合专家模型', category: 'technique', value: 1, symbolSize: 14 },
  ],
  links: [{ source: 'e12', target: 'c3', predicate: '采用', value: 0.7 }],
  categories: [{ name: 'org' }, { name: 'product' }, { name: 'technique' }],
  truncated: false,
}

async function mountAt(path: string) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/graph', component: GraphView },
      { path: '/wiki/:id', component: { template: '<div>entry</div>' } },
    ],
  })
  router.push(path)
  await router.isReady()
  const wrapper = mount(GraphView, { global: { plugins: [router, Antd] } })
  await flushPromises()
  return { wrapper, router }
}

/** Stands in for a click on the canvas; ECharts itself is mocked out above. */
function clickNode(wrapper: VueWrapper, id: string, name: string) {
  wrapper.findComponent(GraphChart).vm.$emit('nodeClick', id, name)
  return flushPromises()
}

function lastGraphCall() {
  return mockedGetGraph.mock.calls.at(-1)?.[0]
}

describe('GraphView node clicks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGetGraph.mockResolvedValue(sample)
    mockedGetEntity.mockResolvedValue({ name: 'OpenAI' } as Awaited<ReturnType<typeof getEntity>>)
    mockedGetConcept.mockResolvedValue({
      name: '混合专家模型',
    } as Awaited<ReturnType<typeof getConcept>>)
  })

  it('focuses the graph on a node clicked in the full graph, rather than leaving the page', async () => {
    const { wrapper, router } = await mountAt('/graph')
    mockedGetGraph.mockClear()

    await clickNode(wrapper, 'e12', 'OpenAI')

    expect(router.currentRoute.value.path).toBe('/graph')
    expect(router.currentRoute.value.query.center).toBe('e12')
    expect(lastGraphCall()).toMatchObject({ center: 'e12', depth: 1 })
    expect(wrapper.text()).toContain('以 OpenAI 为中心的关系网络')
  })

  it('names the centre from the clicked node, without a round trip for what it already knows', async () => {
    const { wrapper } = await mountAt('/graph')

    await clickNode(wrapper, 'c3', '混合专家模型')

    expect(wrapper.text()).toContain('以 混合专家模型 为中心的关系网络')
    expect(mockedGetEntity).not.toHaveBeenCalled()
    expect(mockedGetConcept).not.toHaveBeenCalled()
  })

  it('opens the entry when a second click lands on an entity inside the ego graph', async () => {
    const { wrapper, router } = await mountAt('/graph?center=e12')

    await clickNode(wrapper, 'e45', 'GPT-5')

    expect(router.currentRoute.value.path).toBe('/wiki/45')
  })

  it('re-centres instead of navigating for a concept, which has no entry page of its own', async () => {
    const { wrapper, router } = await mountAt('/graph?center=e12')

    await clickNode(wrapper, 'c3', '混合专家模型')

    expect(router.currentRoute.value.path).toBe('/graph')
    expect(router.currentRoute.value.query.center).toBe('c3')
  })

  it('pushes history when focusing, so Back returns to the full graph', async () => {
    const { wrapper, router } = await mountAt('/graph')
    const push = vi.spyOn(router, 'push')
    const replace = vi.spyOn(router, 'replace')

    await clickNode(wrapper, 'e12', 'OpenAI')

    // A filter tweak replaces (see writeQuery); focusing is a navigation step,
    // and Back has to land on the full graph rather than skip past it. The
    // route assertion keeps this from passing on a push to the entry page.
    expect(router.currentRoute.value.query.center).toBe('e12')
    expect(push).toHaveBeenCalledTimes(1)
    expect(replace).not.toHaveBeenCalled()
  })

  it('loads the graph once per click, not once for the click and again for the URL it wrote', async () => {
    const { wrapper } = await mountAt('/graph')
    mockedGetGraph.mockClear()

    await clickNode(wrapper, 'e12', 'OpenAI')

    expect(mockedGetGraph).toHaveBeenCalledTimes(1)
  })

  it('still reacts to a centre arriving from outside, such as the entry page link', async () => {
    const { wrapper, router } = await mountAt('/graph')
    mockedGetGraph.mockClear()

    await router.push('/graph?center=e45')
    await flushPromises()

    expect(lastGraphCall()).toMatchObject({ center: 'e45' })
    expect(mockedGetEntity).toHaveBeenCalledWith(45)
    expect(wrapper.text()).toContain('为中心的关系网络')
  })

  it('resolves a concept centre arriving from outside through the concept endpoint', async () => {
    const { wrapper } = await mountAt('/graph?center=c3')

    expect(mockedGetConcept).toHaveBeenCalledWith(3)
    expect(wrapper.text()).toContain('以 混合专家模型 为中心的关系网络')
  })

  it('tells the canvas what a click will do, which differs between the two views', async () => {
    const { wrapper } = await mountAt('/graph')
    expect(wrapper.findComponent(GraphChart).props('clickHint')).toBe('点击聚焦到该节点')

    const ego = await mountAt('/graph?center=e12')
    expect(ego.wrapper.findComponent(GraphChart).props('clickHint')).toBe('点击进入词条')
  })
})
