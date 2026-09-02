<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GraphChart as EChartsGraphChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { escapeHtml } from '@/utils/escapeHtml'
import type { GraphData } from '@/types/wiki'

echarts.use([EChartsGraphChart, TooltipComponent, LegendComponent, CanvasRenderer])

// Showing every name at once turns a few hundred nodes into a wall of text.
// Hubs keep a permanent label; everything else reveals its name on hover via
// `emphasis.label`, so nothing is actually hidden — it just is not shouted.
const ALWAYS_LABEL_DEGREE = 3
// Above this many nodes even the hubs go quiet, because "hub" stops being rare.
const LABEL_ALL_BELOW = 40
// How far the pointer may travel between press and release and still count as a
// click. Nodes are `draggable`, and the browser fires `click` after a drag as
// long as it ends on the same element — so without this, dragging one node to
// untangle the layout also fires whatever a click on it does. Observed in a
// real browser: three drags, three unintended activations.
const CLICK_SLOP_PX = 5

const props = withDefaults(defineProps<{ data: GraphData; clickHint?: string }>(), {
  // What a click does is the caller's business — this component still knows
  // nothing about routes — but the hint has to match it, or it lies.
  clickHint: '点击聚焦到该节点',
})
const emit = defineEmits<{ nodeClick: [id: string, name: string] }>()

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

/** Force parameters that hold their shape across two orders of magnitude.
 *
 * One fixed set cannot do that: the spacing that lets a 13-node ego graph
 * breathe pushes 150 nodes off the canvas entirely. Note the direction — as
 * the graph grows the nodes need *less* room each and *more* gravity, because
 * the canvas does not grow with them. (ECharts has no auto-fit for force
 * layouts; roam is a fallback, not a substitute for landing on screen.)
 */
function forceLayout(nodeCount: number) {
  const t = Math.min(1, Math.max(0, (nodeCount - 20) / 180))
  return {
    repulsion: Math.round(220 - 160 * t),
    edgeLength: [Math.round(60 - 25 * t), Math.round(140 - 80 * t)] as [number, number],
    gravity: 0.05 + 0.13 * t,
    friction: 0.6,
  }
}

// The backend already shapes nodes/links/categories for ECharts' `graph`
// series (ARCHITECTURE 4.2) — this only adds presentation on top.
function buildOption(data: GraphData): EChartsOption {
  const labelEverything = data.nodes.length <= LABEL_ALL_BELOW

  return {
    tooltip: {
      // ECharts renders this string as HTML. `name` and `predicate` are LLM
      // output derived from scraped articles, so they are escaped rather than
      // trusted. See utils/escapeHtml.ts.
      formatter: (params) => {
        const item = Array.isArray(params) ? params[0] : params
        if (item.dataType === 'edge') {
          const link = item.data as { predicate?: string }
          return escapeHtml(link.predicate ?? '')
        }
        const node = item.data as { name?: string; value?: number }
        const name = escapeHtml(node.name ?? '')
        return node.value
          ? `${name}<br/><span style="opacity:.7">${node.value} 条关系</span>`
          : name
      },
    },
    legend: [
      {
        data: data.categories.map((category) => category.name),
        top: 0,
        textStyle: { color: '#6b7078', fontSize: 11 },
      },
    ],
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        // Keep the layout box clear of the legend and of the hint line at the
        // bottom left; otherwise nodes settle underneath both.
        top: 34,
        bottom: 28,
        left: 20,
        right: 20,
        categories: data.categories,
        data: data.nodes.map((node) => ({
          ...node,
          label: { show: labelEverything || node.value >= ALWAYS_LABEL_DEGREE },
        })),
        links: data.links,
        force: forceLayout(data.nodes.length),
        label: { position: 'right', fontSize: 11, color: '#17181c' },
        emphasis: {
          // Dim everything outside the hovered node's neighbourhood, so one
          // hover answers "what is this connected to" without any clicking.
          // (`blurScope` is left at its default: there is one series here, so
          // the coordinate-system scope it already uses is the whole canvas.)
          focus: 'adjacency',
          label: { show: true, fontWeight: 'bold' },
          lineStyle: { width: 2.5, opacity: 0.9 },
          edgeLabel: {
            show: true,
            fontSize: 10,
            formatter: (params) =>
              escapeHtml(String((params.data as { predicate?: string }).predicate ?? '')),
          },
        },
        lineStyle: { color: 'source', curveness: 0.12, opacity: 0.28 },
      },
    ],
  }
}

function render() {
  chart?.setOption(buildOption(props.data), true)
}

function handleResize() {
  chart?.resize()
}

/** Re-run the force layout from scratch. Exposed for the toolbar's reset. */
function reset() {
  render()
}
defineExpose({ reset })

const nodeCount = computed(() => props.data.nodes.length)

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  render()
  // Compared against the release position rather than tracked as a "moved"
  // flag, so a node drifting under a stationary cursor (the force layout is
  // still settling) stays clickable.
  let pressedAt: { x: number; y: number } | null = null
  chart.getZr().on('mousedown', (event) => {
    pressedAt = { x: event.offsetX, y: event.offsetY }
  })

  chart.on('click', (params) => {
    if (params.dataType !== 'node') return
    const released = params.event
    if (
      pressedAt &&
      released &&
      Math.hypot(released.offsetX - pressedAt.x, released.offsetY - pressedAt.y) > CLICK_SLOP_PX
    ) {
      return
    }
    // The name goes along with the id: the caller labels the ego view from
    // it straight away, instead of re-fetching a name already on the canvas.
    const node = params.data as { id: string; name?: string }
    emit('nodeClick', String(node.id), String(node.name ?? ''))
  })
  window.addEventListener('resize', handleResize)
})

watch(() => props.data, render)

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="graph-chart">
    <div ref="el" class="graph-chart__canvas"></div>
    <p class="graph-chart__hint mono">
      {{ nodeCount }} 个节点 · 滚轮缩放，拖拽平移，悬停高亮邻居，{{ props.clickHint }}
    </p>
  </div>
</template>

<style scoped lang="scss">
.graph-chart {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 560px;
}

.graph-chart__canvas {
  width: 100%;
  height: 100%;
}

.graph-chart__hint {
  position: absolute;
  left: var(--space-3);
  bottom: var(--space-2);
  margin: 0;
  font-size: 11px;
  color: var(--color-text-muted);
  pointer-events: none;
}
</style>
