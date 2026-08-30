<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { getGraph } from '@/api/wiki'
import GraphChart from './components/GraphChart.vue'
import LoadingPanel from '@/components/LoadingPanel.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { ENTITY_TYPE_OPTIONS } from '@/constants/entityTypes'
import type { EntityType, GraphData } from '@/types/wiki'

// Mirrors the backend's hard cap (apps/wiki/services/graph.py::MAX_LIMIT).
// Used once on mount to discover every concept namespace that exists — the
// `categories` in a filtered/truncated response only covers surviving nodes,
// so it can't be trusted to populate the namespace filter's own option list.
const GRAPH_MAX_LIMIT = 500
const NODE_LIMIT_MIN = 20
const NODE_LIMIT_MAX = 300
const NODE_LIMIT_STEP = 10

const router = useRouter()

const entityTypes = ref<EntityType[]>([])
const namespaces = ref<string[]>([])
const nodeLimit = ref(150)
const namespaceOptions = ref<{ value: string; label: string }[]>([])

const loading = ref(true)
const errorMessage = ref('')
const graph = ref<GraphData | null>(null)

async function loadFilterOptions() {
  try {
    const data = await getGraph({ limit: GRAPH_MAX_LIMIT })
    const knownEntityTypes = new Set<string>(ENTITY_TYPE_OPTIONS.map((option) => option.value))
    namespaceOptions.value = data.categories
      .map((category) => category.name)
      .filter((name) => !knownEntityTypes.has(name))
      .map((name) => ({ value: name, label: name }))
  } catch {
    // The namespace filter just stays empty; the main fetch below surfaces
    // its own error state if the API is actually unreachable.
  }
}

async function loadGraph() {
  loading.value = true
  errorMessage.value = ''
  try {
    graph.value = await getGraph({
      entity_type: entityTypes.value.join(',') || undefined,
      namespace: namespaces.value.join(',') || undefined,
      limit: nodeLimit.value,
    })
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch([entityTypes, namespaces, nodeLimit], () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadGraph, 300)
})

onMounted(() => {
  loadFilterOptions()
  loadGraph()
})

// Concepts have no detail page yet (no /concept/:id route) — same call as
// D9's LinkageGroup, kept consistent rather than linking somewhere that 404s.
function handleNodeClick(id: string) {
  const kind = id.charAt(0)
  const numericId = id.slice(1)
  if (kind === 'e') {
    router.push(`/wiki/${numericId}`)
  } else {
    message.info('概念页面暂未开放，敬请期待。')
  }
}

const isEmpty = computed(
  () =>
    !loading.value && !errorMessage.value && graph.value !== null && graph.value.nodes.length === 0,
)
</script>

<template>
  <section class="graph-view">
    <header class="graph-view__toolbar">
      <div class="graph-view__filter">
        <label class="graph-view__label">实体类型</label>
        <a-select
          v-model:value="entityTypes"
          mode="multiple"
          :options="ENTITY_TYPE_OPTIONS"
          placeholder="全部类型"
          allow-clear
          class="graph-view__select"
        />
      </div>

      <div class="graph-view__filter">
        <label class="graph-view__label">概念命名空间</label>
        <a-select
          v-model:value="namespaces"
          mode="multiple"
          :options="namespaceOptions"
          placeholder="全部命名空间"
          allow-clear
          class="graph-view__select"
        />
      </div>

      <div class="graph-view__filter graph-view__filter--slider">
        <label class="graph-view__label"
          >节点数上限 <span class="mono">{{ nodeLimit }}</span></label
        >
        <a-slider
          v-model:value="nodeLimit"
          :min="NODE_LIMIT_MIN"
          :max="NODE_LIMIT_MAX"
          :step="NODE_LIMIT_STEP"
          class="graph-view__slider"
        />
      </div>
    </header>

    <div class="graph-view__canvas">
      <LoadingPanel v-if="loading" tip="加载关系图谱中…" />
      <ErrorState v-else-if="errorMessage" :message="errorMessage" @retry="loadGraph" />
      <EmptyState
        v-else-if="isEmpty"
        title="暂无图谱数据"
        description="换个筛选条件，或等下一次抽取跑完再来。"
      />
      <template v-else-if="graph">
        <div v-if="graph.truncated" class="graph-view__truncated-banner">
          仅显示关系最多的 {{ graph.nodes.length }} 个节点
        </div>
        <GraphChart :data="graph" @node-click="handleNodeClick" />
      </template>
    </div>
  </section>
</template>

<style scoped lang="scss">
.graph-view {
  padding: var(--space-6) var(--space-5) var(--space-8);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.graph-view__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
  margin-bottom: var(--space-5);
}

.graph-view__filter {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.graph-view__label {
  font-size: 11px;
  color: var(--color-text-muted);
}

.graph-view__select {
  width: 240px;
}

.graph-view__filter--slider {
  width: 220px;
}

.graph-view__slider {
  margin: var(--space-2) var(--space-1) 0;
}

.graph-view__canvas {
  position: relative;
  flex: 1;
  min-height: 560px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.graph-view__truncated-banner {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  z-index: 1;
  background: var(--color-accent-soft);
  color: var(--color-accent-strong);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-pill);
  padding: var(--space-1) var(--space-3);
  font-size: 12px;
}
</style>
