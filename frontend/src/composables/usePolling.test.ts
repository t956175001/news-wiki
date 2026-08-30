import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { usePolling } from './usePolling'

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('polls until a success status', async () => {
    let calls = 0
    const fetchFn = vi.fn(async () => {
      calls++
      return { status: calls < 3 ? 'running' : 'success' }
    })

    const { start, isPolling } = usePolling(fetchFn, 1000)
    start()
    expect(isPolling.value).toBe(true)

    // advance 2 intervals
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetchFn).toHaveBeenCalledTimes(2)

    // advance 1 more to hit 'success'
    await vi.advanceTimersByTimeAsync(1000)
    expect(isPolling.value).toBe(false)
  })

  it('stops on failed status', async () => {
    const fetchFn = vi.fn(async () => ({ status: 'failed' }))
    const { start, isPolling } = usePolling(fetchFn, 1000)
    start()
    await vi.advanceTimersByTimeAsync(1000)
    expect(isPolling.value).toBe(false)
  })
})
