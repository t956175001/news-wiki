<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import type { GraphData } from '@/types/wiki'

const props = defineProps<{ data: GraphData }>()
const emit = defineEmits<{ nodeClick: [id: string] }>()

const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

// The backend already shapes nodes/links/categories for ECharts' `graph`
// series (ARCHITECTURE 4.2) — this passes them straight through.
function buildOption(data: GraphData): EChartsOption {
  return {
    tooltip: {
      formatter: (params) => {
        const item = Array.isArray(params) ? params[0] : params
        if (item.dataType === 'edge') {
          const link = item.data as { predicate?: string }
          return link.predicate ?? ''
        }
        const node = item.data as { name?: string }
        return node.name ?? ''
      },
    },
    legend: [
      {
        data: data.categories.map((category) => category.name),
        top: 0,
        textStyle: { color: 'var(--color-text-muted)', fontSize: 11 },
      },
    ],
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        label: { show: true, position: 'right', fontSize: 11 },
        categories: data.categories,
        data: data.nodes,
        links: data.links,
        force: {
          repulsion: 140,
          edgeLength: [40, 120],
          gravity: 0.12,
          friction: 0.6,
        },
        emphasis: { focus: 'adjacency', lineStyle: { width: 2.5 } },
        lineStyle: { color: 'source', curveness: 0.1, opacity: 0.35 },
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

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  render()
  chart.on('click', (params) => {
    if (params.dataType === 'node') {
      emit('nodeClick', String((params.data as { id: string }).id))
    }
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
  <div ref="el" class="graph-chart"></div>
</template>

<style scoped lang="scss">
.graph-chart {
  width: 100%;
  height: 100%;
  min-height: 560px;
}
</style>
