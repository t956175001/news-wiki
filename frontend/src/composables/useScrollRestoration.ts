import { onBeforeUnmount, type Ref } from 'vue'
import { useRouter } from 'vue-router'

/** How long to keep trying to restore before giving up. */
const RESTORE_TIMEOUT_MS = 1500

/**
 * Remember and restore the scroll offset of an inner scroll container.
 *
 * vue-router's own `savedPosition` reads and writes `window.scrollY`, and this
 * app never scrolls the window: the shell is `height: 100vh; overflow: hidden`
 * and only `.app-shell__content` scrolls. So back-from-an-entry-page always
 * landed at the top of the list you had scrolled halfway down.
 *
 * Keyed on `fullPath` rather than on a popstate flag, which gets the intent
 * right without having to detect the direction of travel: a first visit has no
 * stored offset and starts at the top, and any return to a path you have
 * already scrolled — back button or not — picks up where you left off.
 */
export function useScrollRestoration(container: Ref<HTMLElement | null>) {
  const router = useRouter()
  const offsets = new Map<string, number>()
  let cancelRestore: (() => void) | null = null

  /**
   * Keep assigning `scrollTop` until it sticks.
   *
   * A single assignment after `nextTick` is not enough and the reason is worth
   * spelling out: the destination view mounts in a loading state and fetches
   * its data, so at that moment the container is one skeleton tall. Assigning
   * 400 to an element that can only scroll to 0 silently clamps to 0, and by
   * the time the list arrives the offset has already been "restored".
   */
  function restore(target: number) {
    cancelRestore?.()
    const el = container.value
    if (!el) return
    if (target <= 0) {
      el.scrollTop = 0
      return
    }

    const deadline = performance.now() + RESTORE_TIMEOUT_MS
    let frame = 0
    let cancelled = false

    // Someone scrolling during the retry window has overruled us.
    const abort = () => {
      cancelled = true
      cancelAnimationFrame(frame)
      el.removeEventListener('wheel', abort)
      el.removeEventListener('touchstart', abort)
    }
    el.addEventListener('wheel', abort, { once: true, passive: true })
    el.addEventListener('touchstart', abort, { once: true, passive: true })
    cancelRestore = abort

    const tick = () => {
      if (cancelled || container.value !== el) return
      el.scrollTop = target
      if (el.scrollTop < target && performance.now() < deadline) {
        frame = requestAnimationFrame(tick)
      } else {
        abort()
      }
    }
    frame = requestAnimationFrame(tick)
  }

  const stopBefore = router.beforeEach((to, from) => {
    if (container.value && from.fullPath !== to.fullPath) {
      offsets.set(from.fullPath, container.value.scrollTop)
    }
  })

  const stopAfter = router.afterEach((to) => {
    restore(offsets.get(to.fullPath) ?? 0)
  })

  onBeforeUnmount(() => {
    cancelRestore?.()
    stopBefore()
    stopAfter()
  })
}
