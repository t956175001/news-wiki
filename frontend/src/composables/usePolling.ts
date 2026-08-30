import { ref, onUnmounted, getCurrentInstance } from 'vue'

export const TERMINAL_STATUSES = ['done', 'success', 'partial', 'failed'] as const

export function usePolling(fetchFn: () => Promise<{ status: string }>, intervalMs = 2000) {
  const data = ref<{ status: string } | null>(null)
  const isPolling = ref(false)
  let timerId: ReturnType<typeof setTimeout> | null = null

  const stop = () => {
    isPolling.value = false
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
  }

  const tick = async () => {
    if (!isPolling.value) return
    try {
      const result = await fetchFn()
      data.value = result
      if ((TERMINAL_STATUSES as readonly string[]).includes(result.status)) {
        stop()
        return
      }
    } catch {
      // Polling failure isn't terminal — keep trying on the next tick.
    }
    if (isPolling.value) {
      timerId = setTimeout(tick, intervalMs)
    }
  }

  const start = () => {
    if (isPolling.value) return
    isPolling.value = true
    timerId = setTimeout(tick, intervalMs)
  }

  if (getCurrentInstance()) {
    onUnmounted(stop)
  }

  return { data, isPolling, start, stop }
}
