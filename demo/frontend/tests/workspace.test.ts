import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import WorkspaceView from '../src/views/WorkspaceView.vue'

const session = { id: 'session-1', title: '订单咨询', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', message_count: 0, status: 'open' }
const trace = { id: 'trace-1', session_id: session.id, created_at: '2026-01-01T00:00:01Z', duration_ms: 18, steps: [], decision: { intent: 'order_query', domains: ['order'], confidence: 0.9, provider: 'local_rules', need_human: false, multi_intent: false }, route: 'order.lookup' }
const chatResponse = { message: { id: 'assistant-1', session_id: session.id, role: 'assistant', content: '已从演示服务收到回复', created_at: '2026-01-01T00:00:02Z' }, decision: trace.decision, trace, citations: [], actions: [], quick_replies: [] }
let calls: Array<{ url: string; init?: RequestInit }> = []
let failNextChat = false

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  calls = []
  failNextChat = false
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    if (url.endsWith('/sessions') && init?.method === 'POST') return jsonResponse({ session, welcome_message: '欢迎', quick_replies: [] })
    if (url.endsWith('/sessions')) return jsonResponse({ sessions: [session] })
    if (url.endsWith('/messages')) return jsonResponse({ messages: [] })
    if (url.endsWith('/chat')) {
      if (failNextChat) {
        failNextChat = false
        return jsonResponse({ detail: '服务端拒绝请求' }, 503)
      }
      return jsonResponse(chatResponse)
    }
    throw new Error(`Unexpected API request: ${url}`)
  }))
})

afterEach(() => vi.unstubAllGlobals())

describe('会话消息联动', () => {
  it('服务端欢迎消息带空轨迹时，新会话仍可显示并继续发送', async () => {
    const welcome = { id: 'welcome-1', session_id: session.id, role: 'assistant', content: '欢迎使用演示客服', created_at: session.created_at, trace: {}, citations: [], actions: [] }
    const normalFetch = globalThis.fetch
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      if (String(input).endsWith('/messages')) return jsonResponse({ messages: [welcome] })
      return normalFetch(input, init)
    }))
    const errors: unknown[] = []
    const wrapper = mount(WorkspaceView, { props: { status: null }, global: { config: { errorHandler: (error) => { errors.push(error) } } } })
    try {
      await flushPromises()
      expect(errors).toEqual([])
      expect(wrapper.text()).toContain('欢迎使用演示客服')
      expect(wrapper.text()).toContain('发送消息后')
      await wrapper.get('textarea').setValue('查询订单 DEMO20261017001')
      await wrapper.get('textarea').trigger('keydown', { key: 'Enter', shiftKey: false })
      await flushPromises()
      expect(errors).toEqual([])
      expect(wrapper.text()).toContain('已从演示服务收到回复')
    } finally {
      wrapper.unmount()
    }
  })

  it('只在 API 成功后显示输入与服务端回复，并使用演示聊天契约', async () => {
    const wrapper = mount(WorkspaceView, { props: { status: null } })
    await flushPromises()
    const textarea = wrapper.get('textarea')
    await textarea.setValue('查询订单 DEMO20261017001')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: false })
    await flushPromises()

    expect(calls.some((call) => call.url.endsWith('/api/demo/chat'))).toBe(true)
    const chatCall = calls.find((call) => call.url.endsWith('/api/demo/chat'))
    expect(JSON.parse(String(chatCall?.init?.body))).toEqual({ session_id: 'session-1', content: '查询订单 DEMO20261017001' })
    expect(wrapper.find('.message-row--user .message-bubble').text()).toBe('查询订单 DEMO20261017001')
    expect(wrapper.text()).toContain('已从演示服务收到回复')
    wrapper.unmount()
  })

  it('服务端失败时保留草稿、显示错误与可操作的重试，不显示成功回复', async () => {
    failNextChat = true
    const wrapper = mount(WorkspaceView, { props: { status: null } })
    await flushPromises()
    await wrapper.get('textarea').setValue('查询订单 DEMO20261017001')
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', shiftKey: false })
    await flushPromises()

    expect(wrapper.text()).toContain('服务端拒绝请求')
    expect(wrapper.text()).toContain('重试')
    expect(wrapper.get('textarea').element.value).toBe('查询订单 DEMO20261017001')
    expect(wrapper.text()).not.toContain('已从演示服务收到回复')
    wrapper.unmount()
  })
})
