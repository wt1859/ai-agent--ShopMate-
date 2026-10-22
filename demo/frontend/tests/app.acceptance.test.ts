import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { Component } from 'vue'

const modules = import.meta.glob('../src/App.vue', { eager: true })

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    const payload = url.endsWith('/status')
      ? { mode: 'demo', intent_provider: 'local_rules', embedding_provider: 'local', llm_provider: 'template', jev_configured: false, llm_configured: false, documents: 0, orders: 0, products: 0, features: [], warning: '演示' }
      : url.endsWith('/sessions') ? { sessions: [] }
        : url.endsWith('/messages') ? { messages: [] }
          : { documents: [], categories: [] }
    return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }))
})

afterEach(() => {
  window.location.hash = ''
  vi.unstubAllGlobals()
})

describe('中文客服工作台入口', () => {
  it('提供四个独立路由，知识库不保留会话面板', async () => {
    const App = (modules['../src/App.vue'] as { default: Component } | undefined)?.default
    expect(App, '应存在可挂载的中文客服工作台').toBeDefined()
    const wrapper = mount(App!)
    await flushPromises()
    expect(wrapper.text()).toContain('客服工作台')
    expect(wrapper.text()).toContain('知识库')
    expect(wrapper.text()).toContain('订单与商品')
    expect(wrapper.text()).toContain('执行记录')
    expect(wrapper.find('[data-page="workspace"]').exists()).toBe(true)
    window.location.hash = '#/knowledge'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-page="knowledge"]').exists()).toBe(true)
    expect(wrapper.find('[data-page="workspace"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
