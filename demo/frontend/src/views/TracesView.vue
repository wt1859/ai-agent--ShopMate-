<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { api } from '../api'
import type { Metrics, Trace } from '../types'

const traces = ref<Trace[]>([])
const metrics = ref<Metrics | null>(null)
const loading = ref(false)
const error = ref('')
const selectedId = ref('')
const search = ref('')

const selectedTrace = computed(() => traces.value.find((trace) => trace.id === selectedId.value) ?? null)
const filteredTraces = computed(() => traces.value.filter((trace) => `${trace.id} ${trace.route} ${trace.decision.intent} ${trace.decision.provider}`.toLowerCase().includes(search.value.toLowerCase().trim())))

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [traceResponse, metricResponse] = await Promise.all([api.getTraces(), api.getMetrics()])
    traces.value = traceResponse.traces
    metrics.value = metricResponse
    if (!traces.value.some((trace) => trace.id === selectedId.value)) selectedId.value = traces.value[0]?.id ?? ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '执行记录暂不可用。'
  } finally {
    loading.value = false
  }
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

onMounted(loadData)
</script>

<template>
  <section data-page="traces">
    <div v-if="error" class="error-banner"><Icon name="alert" :size="15" />{{ error }}<button class="retry-link" @click="loadData">重试</button></div>
    <div v-if="metrics" class="metric-strip"><div class="metric-cell"><span>SESSIONS</span><strong>{{ metrics.sessions }}</strong></div><div class="metric-cell"><span>MESSAGES</span><strong>{{ metrics.messages }}</strong></div><div class="metric-cell"><span>DOCUMENTS</span><strong>{{ metrics.documents }}</strong></div><div class="metric-cell"><span>ORDERS</span><strong>{{ metrics.orders }}</strong></div><div class="metric-cell"><span>TRACES</span><strong>{{ metrics.traces }}</strong></div></div>
    <div class="trace-layout">
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">执行记录</div><div class="panel-subtitle">{{ filteredTraces.length }} 条 · 来自演示服务</div></div><button class="icon-button" aria-label="刷新执行记录" :disabled="loading" @click="loadData"><Icon name="refresh" :size="16" /></button></div>
        <div class="toolbar-search trace-search"><Icon name="search" :size="15" /><input v-model="search" aria-label="搜索执行记录" placeholder="按意图、路径或 provider 筛选" /></div>
        <div v-if="loading" class="empty-state"><div class="loading-line"><span class="spinner"></span>正在加载执行记录…</div></div>
        <div v-else-if="error && !traces.length" class="empty-state"><div><div class="empty-icon"><Icon name="activity" :size="21" /></div><h3>执行记录暂不可用</h3><p>{{ error }}</p><button class="secondary-button" @click="loadData"><Icon name="refresh" :size="14" />重试</button></div></div>
        <div v-else-if="filteredTraces.length" class="trace-list"><button v-for="trace in filteredTraces" :key="trace.id" class="trace-row" :class="{ 'trace-row--active': selectedId === trace.id }" @click="selectedId = trace.id"><span><span class="trace-row-title">{{ trace.decision.intent }}<small v-if="trace.decision.need_human" class="pill pill--amber" style="margin-left:7px">需人工</small></span><span class="trace-row-meta">{{ formatTime(trace.created_at) }} · {{ trace.route || '未提供 route' }}</span></span><span class="trace-row-meta">{{ trace.duration_ms }}ms</span><span class="pill">{{ trace.decision.provider }}</span></button></div>
        <div v-else class="empty-state"><div><div class="empty-icon"><Icon name="activity" :size="21" /></div><h3>{{ traces.length ? '没有匹配记录' : '暂无执行记录' }}</h3><p>{{ traces.length ? '试试其它关键词。' : '发送一条客服消息后，若服务记录 trace，这里会显示真实步骤。' }}</p></div></div>
      </section>
      <aside class="panel">
        <div class="panel-header"><div><div class="panel-title">记录详情</div><div class="panel-subtitle">执行步骤与决策结果</div></div></div>
        <div v-if="selectedTrace" class="trace-detail"><p class="eyebrow">{{ selectedTrace.id }}</p><h2>{{ selectedTrace.decision.intent }}</h2><div class="trace-detail-meta"><span class="pill">{{ selectedTrace.decision.provider }}</span><span class="pill pill--muted">{{ selectedTrace.duration_ms }} ms</span><span class="pill pill--muted">{{ selectedTrace.decision.need_human ? '需人工介入' : '无需人工' }}</span><span class="pill pill--muted">{{ Math.round(selectedTrace.decision.confidence * 100) }}% confidence</span></div><div class="section-label">ROUTE · {{ selectedTrace.route || '—' }}</div><div class="detail-step" v-for="(step, index) in selectedTrace.steps" :key="`${step.name}-${index}`"><span class="step-mark" :class="{ 'step-mark--fallback': step.status === 'fallback', 'step-mark--blocked': step.status === 'blocked' }"><Icon :name="step.status === 'blocked' ? 'close' : step.status === 'fallback' ? 'alert' : 'check'" :size="10" /></span><div><div class="detail-step-name">{{ step.name }} <small class="step-duration">{{ step.duration_ms }}ms</small></div><div class="detail-step-info">{{ typeof step.details === 'string' ? step.details : step.status }}</div></div></div></div>
        <div v-else class="empty-state"><div><div class="empty-icon"><Icon name="layers" :size="21" /></div><h3>选择一条记录</h3><p>查看该次执行的决策信息、provider 与各处理步骤。</p></div></div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.trace-search { margin: 12px 14px 0; }
@media (max-width: 900px) { .trace-layout { grid-template-columns: 1fr; } }
</style>
