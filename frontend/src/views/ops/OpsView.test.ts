import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import OpsView from './OpsView.vue'
import type { ExtractionRunDetail, ExtractionRunListItem, Stats } from '@/types/ops'

vi.mock('@/api/ops', () => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  getStats: vi.fn(),
}))
vi.mock('@/api/prompts', () => ({
  listPrompts: vi.fn(),
}))

import { getRun, getStats, listRuns } from '@/api/ops'
import { listPrompts } from '@/api/prompts'

const mockedListRuns = vi.mocked(listRuns)
const mockedGetRun = vi.mocked(getRun)
const mockedGetStats = vi.mocked(getStats)
const mockedListPrompts = vi.mocked(listPrompts)

const RUN_ID = 'a'.repeat(32)

const statsFixture: Stats = {
  window_days: 7,
  since: '2026-08-23T00:00:00Z',
  total_runs: 10,
  success_runs: 8,
  success_rate: 0.8,
  total_tokens: 120000,
  total_cost_cny: '2.8300',
  by_status: { running: 1, success: 8, partial: 1, failed: 0 },
}

function runListItem(status: ExtractionRunListItem['status']): ExtractionRunListItem {
  return {
    run_id: RUN_ID,
    status,
    trigger: 'cron',
    articles_in: 5,
    entities_saved: 12,
    concepts_saved: 6,
    linkages_saved: 9,
    total_tokens: 3000,
    cost_cny: '0.0800',
    elapsed_ms: 5000,
    error_message: '',
    started_at: '2026-08-30T00:00:00Z',
    finished_at: status === 'running' ? null : '2026-08-30T00:01:00Z',
  }
}

function runDetail(status: ExtractionRunDetail['status']): ExtractionRunDetail {
  return {
    ...runListItem(status),
    prompt_tokens: 2000,
    completion_tokens: 1000,
    step_metrics: {
      ingest: { status: 'done', elapsed_ms: 1000, fetched: 5, deduped: 0, saved: 5 },
    },
    prompt_versions: { 'wiki.extract_entities': 1 },
  }
}

async function mountOps() {
  const router = createRouter({
    history: createWebHistory(),
    routes: [{ path: '/ops', component: OpsView }],
  })
  router.push('/ops')
  await router.isReady()
  const wrapper = mount(OpsView, { global: { plugins: [router, Antd] } })
  await flushPromises()
  return wrapper
}

describe('OpsView polling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockedListRuns.mockReset()
    mockedGetRun.mockReset()
    mockedGetStats.mockReset()
    mockedListPrompts.mockReset()
    mockedGetStats.mockResolvedValue(statsFixture)
    mockedListPrompts.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('polls a running run every 3s and stops once it reaches a terminal status', async () => {
    mockedListRuns.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [runListItem('running')],
    })
    mockedGetRun
      .mockResolvedValueOnce(runDetail('running'))
      .mockResolvedValueOnce(runDetail('success'))

    const wrapper = await mountOps()
    expect(mockedGetRun).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(mockedGetRun).toHaveBeenCalledTimes(1)
    expect(mockedGetRun).toHaveBeenCalledWith(RUN_ID)

    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(mockedGetRun).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.status-badge--success').exists()).toBe(true)

    // Status is now terminal — a further tick must not fire another request.
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(mockedGetRun).toHaveBeenCalledTimes(2)
  })

  it('never polls a run that is already in a terminal status', async () => {
    mockedListRuns.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [runListItem('success')],
    })

    await mountOps()
    await vi.advanceTimersByTimeAsync(6000)
    await flushPromises()

    expect(mockedGetRun).not.toHaveBeenCalled()
  })
})
