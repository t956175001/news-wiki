import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import PageBack from './PageBack.vue'

const back = vi.fn()
const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ back, push }),
}))

function setHistoryState(state: unknown) {
  Object.defineProperty(window.history, 'state', { value: state, configurable: true })
}

describe('PageBack', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('goes back when there is somewhere to go back to', async () => {
    // The list page keeps its filters in the URL, so the previous history entry
    // is the list as the visitor had it — better than any fixed destination.
    setHistoryState({ back: '/wiki?search=OpenAI&page=3' })
    const wrapper = mount(PageBack, { props: { fallback: '/wiki' } })

    await wrapper.find('button').trigger('click')

    expect(back).toHaveBeenCalledTimes(1)
    expect(push).not.toHaveBeenCalled()
  })

  it('pushes the fallback when the page was opened directly', async () => {
    // A shared link or a new tab: history.back() would do nothing at all, which
    // reads as a broken button.
    setHistoryState({ back: null })
    const wrapper = mount(PageBack, { props: { fallback: '/wiki' } })

    await wrapper.find('button').trigger('click')

    expect(push).toHaveBeenCalledWith('/wiki')
    expect(back).not.toHaveBeenCalled()
  })

  it('survives a history state that is not there at all', async () => {
    setHistoryState(null)
    const wrapper = mount(PageBack, { props: { fallback: '/wiki' } })

    await wrapper.find('button').trigger('click')

    expect(push).toHaveBeenCalledWith('/wiki')
  })

  it('renders the given label', () => {
    setHistoryState(null)
    const wrapper = mount(PageBack, { props: { fallback: '/wiki', label: '返回词条库' } })

    expect(wrapper.text()).toContain('返回词条库')
  })
})
