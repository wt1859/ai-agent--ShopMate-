<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from './components/Icon.vue'
import WorkspaceView from './views/WorkspaceView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import OrdersView from './views/OrdersView.vue'
import TracesView from './views/TracesView.vue'
import { api } from './api'
import type { StatusResponse } from './types'

type RouteName = 'workspace' | 'knowledge' | 'orders' | 'traces'

const routeItems: Array<{ name: RouteName; label: string; icon: string; hint: string }> = [
  { name: 'workspace', label: '客服工作台', icon: 'grid', hint: '会话与回复' },
  { name: 'knowledge', label: '知识库', icon: 'book', hint: '政策与资料' },
  { name: 'orders', label: '订单与商品', icon: 'box', hint: '业务数据' },
  { name: 'traces', label: '执行记录', icon: 'activity', hint: '过程与证据' },
]

const routeMeta: Record<RouteName, { eyebrow: string; title: string; description: string }> = {
  workspace: { eyebrow: 'SERVICE DESK', title: '客服工作台', description: '用可追踪的证据，处理每一条客户请求。' },
  knowledge: { eyebrow: 'KNOWLEDGE BASE', title: '知识库', description: '维护客服可检索的政策、产品与流程资料。' },
  orders: { eyebrow: 'OPERATIONS', title: '订单与商品', description: '查看演示业务数据，不在此处虚构库存或承诺。' },
  traces: { eyebrow: 'RUN HISTORY', title: '执行记录', description: '回看每次请求经过的判断、检索与响应步骤。' },
}

function readRoute(): RouteName {
  if (typeof window === 'undefined') return 'workspace'
  const value = window.location.hash.replace(/^#\/?/, '').split('?')[0]
  return ['workspace', 'knowledge', 'orders', 'traces'].includes(value) ? value as RouteName : 'workspace'
}

const currentRoute = ref<RouteName>(readRoute())
const mobileNavOpen = ref(false)
const status = ref<StatusResponse | null>(null)
const statusLoading = ref(true)
const statusError = ref('')

const currentMeta = computed(() => routeMeta[currentRoute.value])
const statusLabel = computed(() => {
  if (statusLoading.value) return '读取服务状态'
  if (statusError.value) return '服务未连接'
  return status.value?.mode === 'demo' ? '演示模式' : '服务在线'
})
const providerLabel = computed(() => {
  if (!status.value) return 'provider —'
  const intent = status.value.intent_provider === 'jev' ? 'JEV' : 'local_rules'
  return `${intent} · ${status.value.llm_provider}`
})

function navigate(name: RouteName) {
  if (typeof window !== 'undefined') window.location.hash = `#/${name}`
  currentRoute.value = name
  mobileNavOpen.value = false
}

function syncRoute() {
  currentRoute.value = readRoute()
  mobileNavOpen.value = false
}

async function loadStatus() {
  statusLoading.value = true
  statusError.value = ''
  try {
    status.value = await api.getStatus()
  } catch (error) {
    statusError.value = error instanceof Error ? error.message : '无法读取服务状态'
  } finally {
    statusLoading.value = false
  }
}

onMounted(() => {
  window.addEventListener('hashchange', syncRoute)
  void loadStatus()
})

onBeforeUnmount(() => window.removeEventListener('hashchange', syncRoute))
</script>

<template>
  <div class="app-frame">
    <div v-if="mobileNavOpen" class="mobile-scrim" aria-hidden="true" @click="mobileNavOpen = false" />
    <aside class="sidebar" :class="{ 'sidebar--open': mobileNavOpen }">
      <div class="brand-lockup">
        <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
        <div>
          <strong>客服工作台</strong>
          <span>ecommerce service</span>
        </div>
        <button class="icon-button sidebar-close" aria-label="关闭导航" @click="mobileNavOpen = false"><Icon name="close" :size="18" /></button>
      </div>

      <div class="sidebar-section-label">工作区</div>
      <nav class="primary-nav" aria-label="主导航">
        <button
          v-for="item in routeItems"
          :key="item.name"
          class="nav-item"
          :class="{ 'nav-item--active': currentRoute === item.name }"
          :aria-current="currentRoute === item.name ? 'page' : undefined"
          @click="navigate(item.name)"
        >
          <span class="nav-icon"><Icon :name="item.icon" :size="17" /></span>
          <span class="nav-copy"><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
          <Icon v-if="currentRoute === item.name" name="chevron-right" :size="15" />
        </button>
      </nav>

      <div class="sidebar-note">
        <span class="note-kicker">MODE</span>
        <strong>离线体验 · 演示</strong>
        <p>回复与数据来自本地规则和演示接口，不代表实际商家承诺。</p>
      </div>
      <div class="sidebar-footer">
        <span class="status-dot" :class="{ 'status-dot--muted': !!statusError }"></span>
        <span>{{ statusLabel }}</span>
      </div>
    </aside>

    <section class="app-main">
      <header class="topbar">
        <button class="icon-button mobile-menu" aria-label="打开导航" @click="mobileNavOpen = true"><Icon name="menu" :size="20" /></button>
        <div class="breadcrumb"><span>服务台</span><Icon name="chevron-right" :size="14" /><strong>{{ currentMeta.title }}</strong></div>
        <div class="topbar-status">
          <span class="service-chip" :class="{ 'service-chip--warning': !!statusError }"><span class="status-dot" :class="{ 'status-dot--muted': !!statusError }"></span>{{ statusLabel }}</span>
          <span class="provider-chip">{{ providerLabel }}</span>
          <button class="icon-button" aria-label="刷新服务状态" :disabled="statusLoading" @click="loadStatus"><Icon name="refresh" :size="17" /></button>
        </div>
      </header>

      <main class="page-shell">
        <div class="page-heading">
          <div>
            <p class="eyebrow">{{ currentMeta.eyebrow }}</p>
            <h1>{{ currentMeta.title }}</h1>
            <p>{{ currentMeta.description }}</p>
          </div>
          <div v-if="status && currentRoute === 'workspace'" class="heading-context">
            <span class="context-label">服务状态</span>
            <strong>{{ status.warning || '当前为演示环境，所有执行动作均需确认。' }}</strong>
          </div>
        </div>

        <WorkspaceView v-if="currentRoute === 'workspace'" :status="status" />
        <KnowledgeView v-else-if="currentRoute === 'knowledge'" />
        <OrdersView v-else-if="currentRoute === 'orders'" />
        <TracesView v-else-if="currentRoute === 'traces'" />
      </main>
    </section>
  </div>
</template>
