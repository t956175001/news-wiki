<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { getConcept, getEntity, getGraph } from '@/api/wiki'
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
const DEFAULT_NODE_LIMIT = 150
const DEPTH_OPTIONS = [
  { value: 1, label: '直接关系' },
  { value: 2, label: '两跳以内' },
]

const route = useRoute()
const router = useRouter()
const chart = ref<InstanceType<typeof GraphChart> | null>(null)

// The URL is the single source of truth for every control on this page: a
// filtered graph is then shareable, bookmarkable, and — the reason this
// changed — still there after hitting Back from an entry page.
const entityTypes = ref<EntityType[]>([])
const namespaces = ref<string[]>([])
const nodeLimit = ref(DEFAULT_NODE_LIMIT)
const connectedOnly = ref(true)
const center = ref<string | null>(null)
const depth = ref(1)

const namespaceOptions = ref<{ value: string; label: string }[]>([])
const centerName = ref('')

const loading = ref(true)
const errorMessage = ref('')
const graph = ref<GraphData | null>(null)

function asList(value: unknown): string[] {
  if (typeof value !== 'string' || !value) return []
  return value.split(',').filter(Boolean)
}

function readQuery() {
  const query = route.query
  entityTypes.value = asList(query.entity_type) as EntityType[]
  namespaces.value = asList(query.namespace)
  nodeLimit.value = Number(query.limit) || DEFAULT_NODE_LIMIT
  // Absent means the default (hide isolated nodes); only an explicit 0 turns
  // it off, so a bare /graph URL always lands on the readable view.
  connectedOnly.value = query.min_degree !== '0'
  center.value = typeof query.center === 'string' && query.center ? query.center : null
  depth.value = Number(query.depth) || 1
}

function writeQuery({ push = false } = {}) {
  const query: Record<string, string> = {}
  if (entityTypes.value.length) query.entity_type = entityTypes.value.join(',')
  if (namespaces.value.length) query.namespace = namespaces.value.join(',')
  if (nodeLimit.value !== DEFAULT_NODE_LIMIT) query.limit = String(nodeLimit.value)
  if (!connectedOnly.value) query.min_degree = '0'
  if (center.value) {
    query.center = center.value
    if (depth.value !== 1) query.depth = String(depth.value)
  }
  // Filters `replace`: dragging a slider should not bury the previous page
  // under twenty history entries. Focusing a node is the exception — it is a
  // navigation step, and Back has to land on the graph the user came from
  // rather than skip past it to whatever preceded the page.
  if (push) router.push({ query })
  else router.replace({ query })
}

async function loadFilterOptions() {
  try {
    const data = await getGraph({ limit: GRAPH_MAX_LIMIT, min_degree: 0 })
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

/** The centre's display name, for the "以 X 为中心" banner.
 *
 * Only needed when the centre arrives from outside (a deep link, or Back into
 * an ego view); a click already carries the name off the canvas. Falling back
 * to '' leaves the banner showing the raw `e12`/`c3`, which is ugly but at
 * least still true.
 */
async function loadCenterName() {
  const id = center.value
  if (!id) {
    centerName.value = ''
    return
  }
  const pk = Number(id.slice(1))
  try {
    centerName.value = id.startsWith('e') ? (await getEntity(pk)).name : (await getConcept(pk)).name
  } catch {
    centerName.value = ''
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
      min_degree: connectedOnly.value ? 1 : 0,
      center: center.value ?? undefined,
      depth: center.value ? depth.value : undefined,
    })
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch([entityTypes, namespaces, nodeLimit, connectedOnly, depth], () => {
  writeQuery()
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadGraph, 300)
})

// Reacts to the centre arriving from elsewhere — the entry page's
// "在图谱中查看" button pushes /graph?center=e123 onto this same route, and
// Back/Forward walk the focus history the same way. A centre this component
// wrote itself is skipped: it has already loaded, and reacting again would
// mean two requests and a needless name lookup per click.
watch(
  () => route.query.center,
  (value) => {
    if ((typeof value === 'string' && value ? value : null) === center.value) return
    readQuery()
    loadCenterName()
    loadGraph()
  },
)

onMounted(() => {
  readQuery()
  loadFilterOptions()
  loadCenterName()
  loadGraph()
})

function exitEgo() {
  center.value = null
  centerName.value = ''
  writeQuery()
  loadGraph()
}

/** Pull the graph in around one node, keeping the user on the page. */
function focusOn(id: string, name: string) {
  center.value = id
  centerName.value = name
  writeQuery({ push: true })
  loadGraph()
}

/** Two clicks to leave the page: the first focuses the graph on the node, the
 * second — now inside that ego view — opens its entry.
 *
 * The gesture therefore means different things in the two views, which is a
 * real cost; it buys a graph you can explore without being ejected from it by
 * a stray click on a 14px node, and a first click that behaves the same
 * whichever kind of node it lands on.
 */
function handleNodeClick(id: string, name: string) {
  // Concepts have no detail page (no /concept/:id route), so re-centring stays
  // the only useful thing a click on one can do — in the ego view as well.
  if (center.value && id.startsWith('e')) {
    router.push(`/wiki/${id.slice(1)}`)
    return
  }
  if (center.value) message.info('该概念暂无独立词条页，已切换到它的关系网络。')
  focusOn(id, name)
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

      <div v-if="center" class="graph-view__filter">
        <label class="graph-view__label">关系深度</label>
        <a-select v-model:value="depth" :options="DEPTH_OPTIONS" class="graph-view__depth" />
      </div>

      <div class="graph-view__filter graph-view__filter--switch">
        <label class="graph-view__label">只看有关系的节点</label>
        <a-switch v-model:checked="connectedOnly" :disabled="!!center" size="small" />
      </div>

      <div class="graph-view__filter graph-view__filter--action">
        <a-button size="small" @click="chart?.reset()">重新布局</a-button>
      </div>
    </header>

    <div v-if="center" class="graph-view__ego-banner">
      <span
        >以 <strong>{{ centerName || center }}</strong> 为中心的关系网络</span
      >
      <a-button type="link" size="small" @click="exitEgo">查看全图</a-button>
    </div>

    <div class="graph-view__canvas">
      <LoadingPanel v-if="loading" tip="加载关系图谱中…" />
      <ErrorState v-else-if="errorMessage" :message="errorMessage" @retry="loadGraph" />
      <EmptyState
        v-else-if="isEmpty"
        title="暂无图谱数据"
        :description="
          center ? '该节点还没有抽取到关联关系。' : '换个筛选条件，或等下一次抽取跑完再来。'
        "
      />
      <template v-else-if="graph">
        <div v-if="graph.truncated" class="graph-view__truncated-banner">
          仅显示关系最密集的 {{ graph.nodes.length }} 个节点
        </div>
        <GraphChart
          ref="chart"
          :data="graph"
          :click-hint="center ? '点击进入词条' : '点击聚焦到该节点'"
          @node-click="handleNodeClick"
        />
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
  align-items: flex-end;
  gap: var(--space-5);
  margin-bottom: var(--space-4);
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

.graph-view__depth {
  width: 130px;
}

.graph-view__filter--slider {
  width: 220px;
}

.graph-view__filter--switch {
  gap: var(--space-2);
}

.graph-view__filter--action {
  justify-content: flex-end;
}

.graph-view__slider {
  margin: var(--space-2) var(--space-1) 0;
}

.graph-view__ego-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--color-accent-soft);
  border: 1px solid var(--color-accent);
  font-size: 13px;
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
