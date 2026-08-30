<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import type { TableColumnsType } from 'ant-design-vue'
import { getRun, getStats, listRuns } from '@/api/ops'
import { listPrompts } from '@/api/prompts'
import { usePolling } from '@/composables/usePolling'
import LoadingPanel from '@/components/LoadingPanel.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import RunDetail from './components/RunDetail.vue'
import PromptPanel from './components/PromptPanel.vue'
import type { ExtractionRunDetail, ExtractionRunListItem, RunStatus, Stats } from '@/types/ops'
import type { PromptTemplate } from '@/types/prompts'

const PAGE_SIZE = 20
const POLL_INTERVAL_MS = 3000

const TRIGGER_LABELS: Record<string, string> = { cron: '定时', manual: '手动', seed: '种子' }
const STATUS_LABELS: Record<RunStatus, string> = {
  running: '进行中',
  success: '成功',
  partial: '部分成功',
  failed: '失败',
}

const route = useRoute()

// --- stats cards ---------------------------------------------------------

const stats = ref<Stats | null>(null)
const statsLoading = ref(true)
const statsError = ref('')

async function loadStats() {
  statsLoading.value = true
  statsError.value = ''
  try {
    stats.value = await getStats()
  } catch (e) {
    statsError.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
  } finally {
    statsLoading.value = false
  }
}

// --- runs table ------------------------------------------------------------

const runs = ref<ExtractionRunListItem[]>([])
const runsTotal = ref(0)
const runsPage = ref(1)
const runsLoading = ref(true)
const runsError = ref('')
const expandedRunIds = ref<string[]>([])
const runDetails = ref<Record<string, ExtractionRunDetail>>({})

const columns: TableColumnsType = [
  { title: 'Run ID', dataIndex: 'run_id', key: 'run_id', width: 110 },
  { title: '开始时间', dataIndex: 'started_at', key: 'started_at', width: 160 },
  { title: '触发方式', dataIndex: 'trigger', key: 'trigger', width: 90 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 110 },
  { title: '耗时', dataIndex: 'elapsed_ms', key: 'elapsed_ms', width: 90 },
  { title: 'Token', dataIndex: 'total_tokens', key: 'total_tokens', width: 90 },
  { title: '成本', dataIndex: 'cost_cny', key: 'cost_cny', width: 90 },
  { title: '产出（实体/概念/关系）', key: 'output', width: 180 },
]

function toListItem(detail: ExtractionRunDetail): ExtractionRunListItem {
  return {
    run_id: detail.run_id,
    status: detail.status,
    trigger: detail.trigger,
    articles_in: detail.articles_in,
    entities_saved: detail.entities_saved,
    concepts_saved: detail.concepts_saved,
    linkages_saved: detail.linkages_saved,
    total_tokens: detail.total_tokens,
    cost_cny: detail.cost_cny,
    elapsed_ms: detail.elapsed_ms,
    error_message: detail.error_message,
    started_at: detail.started_at,
    finished_at: detail.finished_at,
  }
}

function syncRowFromDetail(detail: ExtractionRunDetail) {
  const index = runs.value.findIndex((run) => run.run_id === detail.run_id)
  const updated = toListItem(detail)
  if (index === -1) {
    runs.value = [updated, ...runs.value]
  } else {
    runs.value = runs.value.map((run, i) => (i === index ? updated : run))
  }
}

// --- polling: any run still "running" when the page loads refreshes itself
// every 3s via usePolling until it reaches a terminal status, then stops.
const pollers = new Map<string, ReturnType<typeof usePolling<ExtractionRunDetail>>>()

function startPollingRun(runId: string) {
  if (pollers.has(runId)) return
  const poller = usePolling<ExtractionRunDetail>(() => getRun(runId), POLL_INTERVAL_MS)
  pollers.set(runId, poller)
  watch(poller.data, (detail) => {
    if (!detail) return
    runDetails.value = { ...runDetails.value, [runId]: detail }
    syncRowFromDetail(detail)
  })
  poller.start()
}

function stopAllPollers() {
  pollers.forEach((poller) => poller.stop())
  pollers.clear()
}

async function loadRuns() {
  runsLoading.value = true
  runsError.value = ''
  try {
    const data = await listRuns({ page: runsPage.value, page_size: PAGE_SIZE })
    runs.value = data.results
    runsTotal.value = data.count
    for (const run of runs.value) {
      if (run.status === 'running') startPollingRun(run.run_id)
    }
  } catch (e) {
    runsError.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
  } finally {
    runsLoading.value = false
  }
}

watch(runsPage, loadRuns)

async function fetchRunDetailOnce(runId: string) {
  try {
    const detail = await getRun(runId)
    runDetails.value = { ...runDetails.value, [runId]: detail }
  } catch {
    // The expanded panel just stays empty; the row itself already has data.
  }
}

// ant-design-vue's Table takes expand config as flat top-level props
// (`expanded-row-keys` / `@expand`), not a nested `expandable` object like
// React antd — the latter silently no-ops since Table doesn't declare an
// `expandable` prop at all. With `expanded-row-keys` controlled, toggling a
// row reports through `@expand`, one row at a time.
async function handleExpand(expanded: boolean, record: ExtractionRunListItem) {
  if (!expanded) {
    expandedRunIds.value = expandedRunIds.value.filter((id) => id !== record.run_id)
    return
  }
  if (!expandedRunIds.value.includes(record.run_id)) {
    expandedRunIds.value = [...expandedRunIds.value, record.run_id]
  }
  if (!runDetails.value[record.run_id]) {
    await fetchRunDetailOnce(record.run_id)
  }
}

// --- deep link from an evidence card's `/ops?run_id=...` ------------------

async function focusRun(runId: string) {
  try {
    const detail = await getRun(runId)
    runDetails.value = { ...runDetails.value, [runId]: detail }
    if (!runs.value.some((run) => run.run_id === runId)) {
      runs.value = [toListItem(detail), ...runs.value]
    }
    if (!expandedRunIds.value.includes(runId)) {
      expandedRunIds.value = [...expandedRunIds.value, runId]
    }
    if (detail.status === 'running') {
      startPollingRun(runId)
    }
    await nextTick()
    document
      .getElementById(`run-row-${runId}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  } catch {
    // Stale or bad run_id in the URL — the table just renders without it.
  }
}

// --- prompts ---------------------------------------------------------------

const prompts = ref<PromptTemplate[]>([])
const promptsLoading = ref(true)
const promptsError = ref('')

async function loadPrompts() {
  promptsLoading.value = true
  promptsError.value = ''
  try {
    prompts.value = await listPrompts()
  } catch (e) {
    promptsError.value = e instanceof Error ? e.message : '加载失败，请稍后重试。'
  } finally {
    promptsLoading.value = false
  }
}

// --- formatting helpers ------------------------------------------------------

function formatDate(value: string) {
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

function formatCost(value: string) {
  return `¥${Number(value).toFixed(2)}`
}

const successRatePercent = computed(() =>
  stats.value ? Math.round(stats.value.success_rate * 100) : 0,
)

onMounted(async () => {
  await Promise.all([loadStats(), loadRuns(), loadPrompts()])
  const runId = route.query.run_id
  if (typeof runId === 'string' && runId) {
    await focusRun(runId)
  }
})

onBeforeUnmount(stopAllPollers)
</script>

<template>
  <section class="ops-view">
    <section class="ops-view__stats">
      <LoadingPanel v-if="statsLoading" tip="加载统计中…" />
      <ErrorState v-else-if="statsError" :message="statsError" @retry="loadStats" />
      <div v-else-if="stats" class="stat-cards">
        <div class="stat-card">
          <span class="stat-card__label">近 {{ stats.window_days }} 天 run 数</span>
          <span class="stat-card__value mono">{{ stats.total_runs }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-card__label">成功率</span>
          <span class="stat-card__value mono">{{ successRatePercent }}%</span>
        </div>
        <div class="stat-card">
          <span class="stat-card__label">总 token</span>
          <span class="stat-card__value mono">{{ stats.total_tokens.toLocaleString() }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-card__label">总成本</span>
          <span class="stat-card__value mono">{{ formatCost(stats.total_cost_cny) }}</span>
        </div>
      </div>
    </section>

    <section class="ops-view__runs">
      <h2 class="ops-view__section-title">抽取记录</h2>
      <LoadingPanel v-if="runsLoading" tip="加载记录中…" />
      <ErrorState v-else-if="runsError" :message="runsError" @retry="loadRuns" />
      <EmptyState v-else-if="runs.length === 0" title="还没有任何抽取记录" />
      <a-table
        v-else
        :columns="columns"
        :data-source="runs"
        row-key="run_id"
        :pagination="{
          current: runsPage,
          pageSize: PAGE_SIZE,
          total: runsTotal,
          onChange: (page: number) => (runsPage = page),
        }"
        :expanded-row-keys="expandedRunIds"
        :custom-row="(record: ExtractionRunListItem) => ({ id: `run-row-${record.run_id}` })"
        @expand="handleExpand"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'run_id'">
            <span class="mono">{{ (record as ExtractionRunListItem).run_id.slice(0, 8) }}</span>
          </template>
          <template v-else-if="column.key === 'started_at'">
            <span class="mono">{{ formatDate((record as ExtractionRunListItem).started_at) }}</span>
          </template>
          <template v-else-if="column.key === 'trigger'">
            {{ TRIGGER_LABELS[(record as ExtractionRunListItem).trigger] }}
          </template>
          <template v-else-if="column.key === 'status'">
            <span
              class="status-badge"
              :class="`status-badge--${(record as ExtractionRunListItem).status}`"
            >
              <span class="status-badge__dot" aria-hidden="true"></span>
              {{ STATUS_LABELS[(record as ExtractionRunListItem).status] }}
            </span>
          </template>
          <template v-else-if="column.key === 'elapsed_ms'">
            <span class="mono">{{ (record as ExtractionRunListItem).elapsed_ms }}ms</span>
          </template>
          <template v-else-if="column.key === 'total_tokens'">
            <span class="mono">{{ (record as ExtractionRunListItem).total_tokens }}</span>
          </template>
          <template v-else-if="column.key === 'cost_cny'">
            <span class="mono">{{ formatCost((record as ExtractionRunListItem).cost_cny) }}</span>
          </template>
          <template v-else-if="column.key === 'output'">
            <span class="mono"
              >{{ (record as ExtractionRunListItem).entities_saved }} /
              {{ (record as ExtractionRunListItem).concepts_saved }} /
              {{ (record as ExtractionRunListItem).linkages_saved }}</span
            >
          </template>
        </template>

        <template #expandedRowRender="{ record }">
          <RunDetail
            v-if="runDetails[(record as ExtractionRunListItem).run_id]"
            :step-metrics="runDetails[(record as ExtractionRunListItem).run_id].step_metrics"
          />
          <LoadingPanel v-else tip="加载分步详情中…" />
        </template>
      </a-table>
    </section>

    <section class="ops-view__prompts">
      <LoadingPanel v-if="promptsLoading" tip="加载 Prompt 中…" />
      <ErrorState v-else-if="promptsError" :message="promptsError" @retry="loadPrompts" />
      <PromptPanel v-else :prompts="prompts" />
    </section>
  </section>
</template>

<style scoped lang="scss">
.ops-view {
  padding: var(--space-6) var(--space-5) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-7);
}

.ops-view__section-title {
  font-size: 16px;
  margin-bottom: var(--space-3);
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-4);
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
}

.stat-card__label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.stat-card__value {
  font-size: 26px;
  font-family: var(--font-display);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
}

.status-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status-badge--success {
  color: var(--color-success);
  background: var(--color-success-soft);
}

.status-badge--partial {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.status-badge--failed {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.status-badge--running {
  color: var(--color-info);
  background: var(--color-info-soft);

  .status-badge__dot {
    border: 1.5px solid currentColor;
    border-top-color: transparent;
    background: none;
    width: 8px;
    height: 8px;
    animation: status-spin 0.8s linear infinite;
  }
}

@keyframes status-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
