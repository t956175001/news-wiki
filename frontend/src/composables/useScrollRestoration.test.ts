import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useScrollRestoration } from './useScrollRestoration'

let beforeHook: ((to: unknown, from: unknown) => void) | undefined
let afterHook: ((to: unknown) => void) | undefined
const stopBefore = vi.fn()
const stopAfter = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({
    beforeEach: (fn: (to: unknown, from: unknown) => void) => {
      beforeHook = fn
      return stopBefore
    },
    afterEach: (fn: (to: unknown) => void) => {
      afterHook = fn
      return stopAfter
    },
  }),
}))

const frames = (count: number) =>
  new Promise<void>((resolve) => {
    let left = count
    const step = () => (left-- > 0 ? requestAnimationFrame(step) : resolve())
    requestAnimationFrame(step)
  })

/**
 * Stands in for `.app-shell__content`. jsdom does no layout, so `scrollTop` is
 * a plain property there and would accept any value — that would hide the very
 * clamping this composable exists to survive. `maxScroll` reproduces it.
 */
type FakeContainer = HTMLElement & { maxScroll: number }

function makeContainer(maxScroll = 1000): FakeContainer {
  const el = document.createElement('div') as unknown as FakeContainer
  let value = 0
  el.maxScroll = maxScroll
  Object.defineProperty(el, 'scrollTop', {
    get: () => value,
    set: (next: number) => {
      value = Math.max(0, Math.min(next, el.maxScroll))
    },
    configurable: true,
  })
  return el
}

function mountWithContainer(el: HTMLElement) {
  const container = ref<HTMLElement | null>(el)
  const wrapper = mount(
    defineComponent({
      setup() {
        useScrollRestoration(container)
        return () => null
      },
    }),
  )
  return { container, wrapper }
}

describe('useScrollRestoration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    beforeHook = undefined
    afterHook = undefined
  })

  it('restores the offset when returning to a path already scrolled', async () => {
    const el = makeContainer()
    mountWithContainer(el)
    el.scrollTop = 420

    beforeHook?.({ fullPath: '/wiki/12' }, { fullPath: '/wiki?page=3' })
    afterHook?.({ fullPath: '/wiki/12' })
    await frames(2)
    expect(el.scrollTop).toBe(0) // fresh path starts at the top

    beforeHook?.({ fullPath: '/wiki?page=3' }, { fullPath: '/wiki/12' })
    afterHook?.({ fullPath: '/wiki?page=3' })
    await frames(2)

    expect(el.scrollTop).toBe(420)
  })

  it('keeps retrying until the destination has actually loaded its content', async () => {
    // The bug this guards: the list mounts as a skeleton, so at first the
    // container can only scroll to 0 and a single assignment is silently
    // clamped away. Real browser check confirmed 400 -> 0 before this fix.
    const el = makeContainer(1000)
    mountWithContainer(el)
    el.scrollTop = 400

    beforeHook?.({ fullPath: '/wiki/12' }, { fullPath: '/wiki?page=3' })
    el.maxScroll = 0 // destination renders a short skeleton
    afterHook?.({ fullPath: '/wiki/12' })
    await frames(2)

    beforeHook?.({ fullPath: '/wiki?page=3' }, { fullPath: '/wiki/12' })
    afterHook?.({ fullPath: '/wiki?page=3' })
    await frames(2)
    expect(el.scrollTop).toBe(0) // nothing to scroll yet

    el.maxScroll = 1000 // data arrives, the list gets tall
    await frames(3)

    expect(el.scrollTop).toBe(400)
  })

  it('stops fighting the user if they scroll during the retry window', async () => {
    const el = makeContainer(1000)
    mountWithContainer(el)
    el.scrollTop = 400

    beforeHook?.({ fullPath: '/wiki/12' }, { fullPath: '/wiki?page=3' })
    el.maxScroll = 0
    afterHook?.({ fullPath: '/wiki/12' })
    await frames(2)
    beforeHook?.({ fullPath: '/wiki?page=3' }, { fullPath: '/wiki/12' })
    afterHook?.({ fullPath: '/wiki?page=3' })
    await frames(2)

    el.dispatchEvent(new Event('wheel'))
    el.maxScroll = 1000
    el.scrollTop = 50
    await frames(3)

    expect(el.scrollTop).toBe(50)
  })

  it('keys on fullPath, so a different filter is a different position', async () => {
    const el = makeContainer()
    mountWithContainer(el)
    el.scrollTop = 300

    beforeHook?.({ fullPath: '/wiki?page=2' }, { fullPath: '/wiki?page=1' })
    afterHook?.({ fullPath: '/wiki?page=2' })
    await frames(2)

    expect(el.scrollTop).toBe(0)
  })

  it('ignores a navigation that does not change the path', async () => {
    // A slider being dragged fires router.replace repeatedly; recording the
    // offset each time would fight with the user's own scrolling.
    const el = makeContainer()
    mountWithContainer(el)
    el.scrollTop = 250

    beforeHook?.({ fullPath: '/graph' }, { fullPath: '/graph' })
    el.scrollTop = 999
    beforeHook?.({ fullPath: '/wiki' }, { fullPath: '/graph' })
    afterHook?.({ fullPath: '/wiki' })
    await frames(2)
    beforeHook?.({ fullPath: '/graph' }, { fullPath: '/wiki' })
    afterHook?.({ fullPath: '/graph' })
    await frames(2)

    expect(el.scrollTop).toBe(999)
  })

  it('unregisters both router hooks on unmount', () => {
    const { wrapper } = mountWithContainer(makeContainer())

    wrapper.unmount()

    expect(stopBefore).toHaveBeenCalledTimes(1)
    expect(stopAfter).toHaveBeenCalledTimes(1)
  })
})
