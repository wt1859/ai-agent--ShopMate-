<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import { api, ApiError } from '../api'
import type { Action, Citation, Message, Session, StatusResponse, Trace } from '../types'

const props = defineProps<{ status: StatusResponse | null }>()
const sessions = ref<Session[]>([])
const selectedSessionId = ref('')
const messages = ref<Message[]>([])
const latestTrace = ref<Trace | null>(null)
const latestCitations = ref<Citation[]>([])
const pendingActions = ref<Action[]>([])
const serverQuickReplies = ref<string[]>([])
const welcomeMessage = ref('')
const sessionsLoading = ref(false)
const messagesLoading = ref(false)
const creatingSession = ref(false)
const sending = ref(false)
const confirmingActionId = ref('')
const errorMessage = ref('')
const draft = ref('')
const drawerCitation = ref<Citation | null>(null)
const scrollArea = ref<HTMLElement | null>(null)
const pendingConfirmation = ref<Action | null>(null)
const lastFailedDraft = ref('')

const selectedSession = computed(() => sessions.value.find((session) => session.id === selectedSessionId.value) ?? null)
const quickScenarios = [
  { label: '7 天无理由', text: '我想申请7天无理由退货' },
  { label: '查询订单', text: '查询订单 DEMO20261017001' },
  { label: '查询库存', text: '查询 SKU-PHONE-001 库存' },
  { label: '取消订单', text: '取消订单 DEMO20261017002' },
  { label: '投诉转人工', text: '我想投诉，请转人工处理' },
  { label: '多轮追问', text: '那可以退款吗' },
]

const availableQuickReplies = computed(() => serverQuickReplies.value.length ? serverQuickReplies.value : quickScenarios.map((item) => item.label))
const latestDecision = computed(() => latestTrace.value?.decision)
const latestProvider = computed(() => latestDecision.value?.provider || latestTrace.value?.steps.find((step) => step.name.toLowerCase().includes('intent'))?.name || props.status?.intent_provider || '—')
const latestRoute = computed(() => latestTrace.value?.route || '')

function setError(error: unknown, fallback: string) {
  errorMessage.value = error instanceof Error ? error.message : fallback
}

function formatTime(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

function formatClock(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

async function scrollToBottom() {
  await nextTick()
  if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight
}

async function loadSessions(preferredId?: string) {
  sessionsLoading.value = true
  errorMessage.value = ''
  try {
    const response = await api.getSessions()
    sessions.value = response.sessions
    const nextId = preferredId && response.sessions.some((session) => session.id === preferredId)
      ? preferredId
      : selectedSessionId.value && response.sessions.some((session) => session.id === selectedSessionId.value)
        ? selectedSessionId.value
        : response.sessions[0]?.id ?? ''
    if (nextId !== selectedSessionId.value) await selectSession(nextId)
    else if (!nextId) clearSessionState()
  } catch (error) {
    setError(error, '无法加载会话，请重试。')
  } finally {
    sessionsLoading.value = false
  }
}

function clearSessionState() {
  selectedSessionId.value = ''
  messages.value = []
  latestTrace.value = null
  latestCitations.value = []
  pendingActions.value = []
  serverQuickReplies.value = []
  welcomeMessage.value = ''
}

async function selectSession(id: string) {
  if (!id) {
    clearSessionState()
    return
  }
  selectedSessionId.value = id
  messages.value = []
  latestTrace.value = null
  latestCitations.value = []
  pendingActions.value = []
  welcomeMessage.value = ''
  messagesLoading.value = true
  errorMessage.value = ''
  try {
    const response = await api.getMessages(id)
    messages.value = response.messages
    const latestReply = [...response.messages].reverse().find((message) => message.role === 'assistant')
    latestTrace.value = latestReply?.trace && Array.isArray(latestReply.trace.steps) ? latestReply.trace : null
    latestCitations.value = latestReply?.citations ?? []
    pendingActions.value = response.messages.flatMap((message) => message.actions ?? []).filter((action) => action.status === 'pending')
    await scrollToBottom()
  } catch (error) {
    setError(error, '无法加载消息，请重试。')
  } finally {
    messagesLoading.value = false
  }
}

async function refreshSelectedSession() {
  if (selectedSessionId.value) await selectSession(selectedSessionId.value)
}

async function createSession() {
  creatingSession.value = true
  errorMessage.value = ''
  try {
    const response = await api.createSession()
    await loadSessions(response.session.id)
    if (selectedSessionId.value !== response.session.id) {
      sessions.value = [response.session, ...sessions.value.filter((session) => session.id !== response.session.id)]
      await selectSession(response.session.id)
    }
    welcomeMessage.value = response.welcome_message
    serverQuickReplies.value = response.quick_replies
  } catch (error) {
    setError(error, '无法创建会话，请重试。')
  } finally {
    creatingSession.value = false
  }
}

async function removeSession() {
  const target = selectedSession.value
  if (!target) return
  if (!window.confirm(`确定删除会话「${target.title}」？`)) return
  errorMessage.value = ''
  try {
    await api.deleteSession(target.id)
    sessions.value = sessions.value.filter((session) => session.id !== target.id)
    clearSessionState()
    if (sessions.value[0]) await selectSession(sessions.value[0].id)
  } catch (error) {
    setError(error, '删除会话失败，请重试。')
  }
}

function fillScenario(label: string) {
  const scenario = quickScenarios.find((item) => item.label === label)
  draft.value = scenario?.text ?? label
}

function submitOnEnter(event: KeyboardEvent) {
  if (!event.shiftKey) {
    event.preventDefault()
    void sendMessage()
  }
}

async function sendMessage(content = draft.value.trim()) {
  if (!content || !selectedSessionId.value || sending.value) return
  draft.value = content
  lastFailedDraft.value = content
  errorMessage.value = ''
  sending.value = true
  try {
    const response = await api.chat(selectedSessionId.value, content)
    const assistantMessage: Message = {
      ...response.message,
      trace: response.trace,
      citations: response.citations,
      actions: response.actions,
    }
    const sentMessage: Message = {
      id: `user-${Date.now()}`,
      session_id: selectedSessionId.value,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }
    messages.value = [...messages.value, sentMessage, assistantMessage]
    lastFailedDraft.value = ''
    latestTrace.value = response.trace
    latestCitations.value = response.citations
    pendingActions.value = response.actions.filter((action) => action.status === 'pending')
    serverQuickReplies.value = response.quick_replies
    draft.value = ''
    await loadSessions(selectedSessionId.value)
    await scrollToBottom()
  } catch (error) {
    setError(error, '消息发送失败，请重试。')
  } finally {
    sending.value = false
  }
}

async function confirmAction(action: Action) {
  confirmingActionId.value = action.id
  errorMessage.value = ''
  try {
    const result = await api.confirmAction(action.id)
    const confirmed = result.action
    pendingActions.value = pendingActions.value.filter((item) => item.id !== action.id)
    const targetMessage = [...messages.value].reverse().find((message) => message.actions?.some((item) => item.id === action.id))
    if (targetMessage?.actions) targetMessage.actions = targetMessage.actions.map((item) => item.id === action.id ? confirmed : item)
    pendingConfirmation.value = null
    await refreshSelectedSession()
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) setError(error, '该操作已失效，请刷新会话。')
    else setError(error, '确认操作失败，请重试。')
  } finally {
    confirmingActionId.value = ''
  }
}

watch(messages, () => { void scrollToBottom() }, { deep: true })
onMounted(() => { void loadSessions() })
</script>

<template>
  <section class="workspace-grid" data-page="workspace">
    <aside class="workspace-column session-column">
      <div class="session-header">
        <div class="session-header-row">
          <div><div class="panel-title">会话记录</div><div class="panel-subtitle">{{ sessions.length }} 条记录</div></div>
          <button class="primary-button small-button" :disabled="creatingSession || sessionsLoading" @click="createSession"><span v-if="creatingSession" class="spinner"></span><Icon v-else name="plus" :size="14" />新建</button>
        </div>
      </div>
      <div v-if="sessionsLoading" class="session-loading"><div class="loading-line"><span class="spinner"></span>正在读取会话…</div></div>
      <div v-else-if="sessions.length" class="session-list">
        <button v-for="session in sessions" :key="session.id" class="session-item" :class="{ 'session-item--active': selectedSessionId === session.id }" @click="selectSession(session.id)">
          <span class="session-item-title">{{ session.title || '未命名会话' }}</span>
          <span class="session-item-meta"><span>{{ formatTime(session.updated_at) }}</span><span>{{ session.message_count }} 条</span></span>
        </button>
      </div>
      <div v-else class="session-empty">{{ errorMessage ? '会话暂不可用。' : '尚无会话。连接演示服务后，可创建并查看真实会话记录。' }}</div>
    </aside>

    <section class="workspace-column chat-column" aria-label="会话消息">
      <header class="chat-header">
        <div class="chat-header-title">
          <h2>{{ selectedSession?.title || '选择或新建会话' }}</h2>
          <p>{{ selectedSession ? `创建于 ${formatTime(selectedSession.created_at)}` : '消息与客服回复会通过演示 API 实时读取' }}</p>
        </div>
        <div class="chat-header-actions">
          <button class="icon-button" aria-label="重新加载消息" :disabled="!selectedSessionId || messagesLoading" @click="refreshSelectedSession"><Icon name="refresh" :size="16" /></button>
          <button v-if="selectedSession" class="icon-button" aria-label="删除会话" @click="removeSession"><Icon name="trash" :size="16" /></button>
        </div>
      </header>

      <div v-if="messagesLoading" class="messages empty-state"><div><div class="loading-line"><span class="spinner"></span>正在加载消息…</div></div></div>
      <div v-else-if="messages.length" ref="scrollArea" class="messages" aria-live="polite">
        <article v-for="message in messages" :key="message.id" class="message-row" :class="message.role === 'user' ? 'message-row--user' : ''">
          <div class="message-avatar">{{ message.role === 'user' ? '访客' : '客服' }}</div>
          <div class="message-body">
            <div class="message-meta"><strong>{{ message.role === 'user' ? '访客' : '客服助手' }}</strong><time>{{ formatClock(message.created_at) }}</time></div>
            <div class="message-bubble">{{ message.content }}</div>
            <div v-if="message.role === 'assistant' && message.citations?.length" class="message-extras">
              <button v-for="citation in message.citations.slice(0, 2)" :key="citation.id" class="quick-chip" @click="drawerCitation = citation">引用 · {{ citation.title }}</button>
              <span v-if="message.citations.length > 2" class="pill pill--muted">另有 {{ message.citations.length - 2 }} 条</span>
            </div>
            <div v-if="message.role === 'assistant' && message.actions?.length" class="message-extras action-stack">
              <div v-for="action in message.actions" :key="action.id" class="action-card">
                <strong>{{ action.label }}</strong><span>订单 {{ action.order_no }}</span>
                <span class="action-status" :class="{ 'action-status--confirmed': action.status === 'confirmed' }">{{ action.status === 'pending' ? '待确认' : '已确认' }}</span>
                <button v-if="action.status === 'pending'" class="danger-button small-button" :disabled="confirmingActionId === action.id" @click="pendingConfirmation = action">{{ confirmingActionId === action.id ? '处理中…' : '确认操作' }}</button>
              </div>
            </div>
          </div>
        </article>
        <div v-if="sending" class="typing-row"><span class="typing-dots"><i></i><i></i><i></i></span>正在等待演示服务响应…</div>
        <div v-if="welcomeMessage" class="message-meta"><span class="pill pill--muted">服务端欢迎语</span><span>{{ welcomeMessage }}</span></div>
      </div>
      <div v-else class="messages empty-state">
        <div>
          <div class="empty-icon"><Icon name="grid" :size="21" /></div>
          <h3>{{ selectedSession ? '会话已就绪' : '开始处理客户请求' }}</h3>
          <p>{{ selectedSession ? (welcomeMessage || '这个会话目前还没有消息。输入内容发送后，回复、引用与执行步骤将由服务端返回。') : '选择左侧会话，或创建一条新会话。所有内容均通过本地演示 API 获取，不会预填虚构回复。' }}</p>
          <button v-if="!selectedSession" class="primary-button" :disabled="creatingSession" @click="createSession"><Icon name="plus" :size="15" />创建真实演示会话</button>
        </div>
      </div>

      <div class="composer-wrap">
        <div class="quick-replies" aria-label="场景快捷填入">
          <button v-for="label in availableQuickReplies" :key="label" class="quick-chip" :disabled="!selectedSessionId || sending" @click="fillScenario(label)">{{ label }}</button>
        </div>
        <div v-if="errorMessage" class="error-banner"><Icon name="alert" :size="15" /><span>{{ errorMessage }}</span><button v-if="lastFailedDraft" class="retry-link" @click="sendMessage(lastFailedDraft)">重试</button><button class="icon-button" aria-label="关闭提示" @click="errorMessage = ''"><Icon name="close" :size="14" /></button></div>
        <div class="composer">
          <textarea v-model="draft" aria-label="输入客户问题" placeholder="输入客户问题…（Enter 发送，Shift + Enter 换行）" :disabled="!selectedSessionId || sending" @keydown.enter="submitOnEnter"></textarea>
          <button class="send-button" aria-label="发送消息" :disabled="!selectedSessionId || !draft.trim() || sending" @click="sendMessage()"><span v-if="sending" class="spinner"></span><Icon v-else name="send" :size="16" /></button>
        </div>
        <div class="composer-footnote"><span>回复来自接口 · 操作需人工确认</span><span>{{ draft.length }} / 2000</span></div>
      </div>
    </section>

    <aside class="workspace-column evidence-column" aria-label="执行步骤与引用">
      <header class="evidence-header"><div><div class="panel-title">追踪与证据</div><div class="panel-subtitle">真实服务返回内容</div></div><Icon name="layers" :size="17" /></header>
      <div v-if="latestTrace" class="evidence-body">
        <div class="trace-intro">
          <h3>请求处理路径</h3><p>{{ latestRoute || '服务未提供路由描述' }}</p>
          <div class="trace-meta"><span class="pill">{{ latestProvider }}</span><span class="pill pill--muted">{{ latestTrace.duration_ms }} ms</span><span v-if="latestDecision" class="pill pill--muted">置信度 {{ Math.round(latestDecision.confidence * 100) }}%</span></div>
        </div>
        <div class="evidence-section">
          <div class="evidence-section-title"><span>执行步骤</span><span>{{ latestTrace.steps.length }}</span></div>
          <div class="step-list">
            <div v-for="(step, index) in latestTrace.steps" :key="`${step.name}-${index}`" class="step-item">
              <span class="step-mark" :class="{ 'step-mark--fallback': step.status === 'fallback', 'step-mark--blocked': step.status === 'blocked' }"><Icon :name="step.status === 'blocked' ? 'close' : step.status === 'fallback' ? 'alert' : 'check'" :size="10" /></span>
              <span class="step-name">{{ step.name }}<small v-if="step.details" class="step-detail">{{ typeof step.details === 'string' ? step.details : '' }}</small></span><span class="step-duration">{{ step.duration_ms }}ms</span>
            </div>
          </div>
        </div>
        <div v-if="latestDecision" class="evidence-section">
          <div class="evidence-section-title"><span>意图识别</span><span>{{ latestDecision.provider }}</span></div>
          <div class="decision-row"><strong>{{ latestDecision.intent }}</strong><span class="pill pill--muted">{{ latestDecision.need_human ? '需人工介入' : '自动处理' }}</span></div>
          <div class="domain-list"><span v-for="domain in latestDecision.domains" :key="domain" class="pill pill--muted">{{ domain }}</span></div>
        </div>
        <div class="evidence-section">
          <div class="evidence-section-title"><span>知识引用</span><span>{{ latestCitations.length }}</span></div>
          <div v-if="latestCitations.length" class="citation-list">
            <button v-for="citation in latestCitations.slice(0, 3)" :key="citation.id" class="citation-item" @click="drawerCitation = citation">
              <strong>{{ citation.title }}</strong><p>{{ citation.content }}</p><span class="citation-meta"><span>{{ citation.category }}</span><span>· {{ citation.source || '演示政策' }}</span><span>· {{ Math.round(citation.score * 100) }}%</span></span>
            </button>
            <button v-if="latestCitations.length > 3" class="link-button" @click="drawerCitation = latestCitations[0]">查看全部 {{ latestCitations.length }} 条引用</button>
          </div>
          <p v-else class="inspector-empty">此次响应没有返回知识库引用。</p>
        </div>
      </div>
      <div v-else class="evidence-body inspector-empty">{{ selectedSession ? '发送消息后，将在这里显示服务端返回的决策信息、执行步骤与真实引用。' : '选择会话后，查看处理证据。' }}</div>
    </aside>
  </section>

  <div v-if="drawerCitation" class="citation-drawer" role="presentation" @click.self="drawerCitation = null">
    <section class="drawer-panel" role="dialog" aria-modal="true" aria-labelledby="citation-title">
      <header class="drawer-header"><div><p class="eyebrow">KNOWLEDGE CITATION</p><h2 id="citation-title">引用详情</h2><p>内容与检索分数来自当前服务响应。</p></div><button class="icon-button" aria-label="关闭引用详情" @click="drawerCitation = null"><Icon name="close" :size="19" /></button></header>
      <div class="drawer-content"><article class="citation-detail"><div class="pill">{{ drawerCitation.category }}</div><h3>{{ drawerCitation.title }}</h3><p>{{ drawerCitation.content }}</p><div class="citation-detail-meta"><span class="pill pill--muted">来源：{{ drawerCitation.source || '演示政策' }}</span><span class="pill pill--muted">版本：{{ drawerCitation.version || '—' }}</span><span class="pill pill--muted">综合分 {{ drawerCitation.score.toFixed(3) }}</span><span class="pill pill--muted">Dense {{ drawerCitation.dense_score.toFixed(3) }}</span><span class="pill pill--muted">BM25 {{ drawerCitation.bm25_score.toFixed(3) }}</span></div></article></div>
    </section>
  </div>

  <div v-if="pendingConfirmation" class="confirm-sheet" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
    <h3 id="confirm-title">确认执行演示操作？</h3><p>即将{{ pendingConfirmation.type === 'cancel_order' ? '取消' : '提交退款申请' }}订单 {{ pendingConfirmation.order_no }}。此操作会提交至演示接口，请确认后继续。</p>
    <div class="confirm-actions"><button class="secondary-button small-button" @click="pendingConfirmation = null">返回</button><button class="danger-button small-button" :disabled="!!confirmingActionId" @click="confirmAction(pendingConfirmation)">{{ confirmingActionId ? '正在提交…' : '确认提交' }}</button></div>
  </div>
</template>

<style scoped>
.session-header-row > div { min-width: 0; }
.action-stack { display: grid; }
.step-detail { display: block; margin-top: 3px; color: var(--muted-2); font-size: 9px; font-weight: 400; }
.decision-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; color: var(--ink); font-size: 10px; }
.domain-list { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
@media (max-width: 900px) { .session-column { display: flex; flex-direction: column; }.session-list { max-height: 116px; } }
@media (max-width: 650px) { .session-column { min-height: 116px; }.session-header { padding: 11px 12px 8px; }.session-list { max-height: none; }.chat-header { padding: 13px; }.chat-header h2 { max-width: 220px; } }
</style>
