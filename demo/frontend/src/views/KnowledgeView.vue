<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { api } from '../api'
import type { Citation, KnowledgeDocument } from '../types'

const documents = ref<KnowledgeDocument[]>([])
const categories = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const query = ref('')
const searchLoading = ref(false)
const searchError = ref('')
const searchResults = ref<Citation[]>([])
const searchMeta = ref<{ strategy: string; embedding_provider: string; duration_ms: number } | null>(null)
const title = ref('')
const content = ref('')
const category = ref('')
const searchDomain = ref('')
const searchDone = ref(false)

const filteredDocuments = computed(() => documents.value.filter((document) => !category.value || document.category === category.value))

async function loadDocuments() {
  loading.value = true
  error.value = ''
  try {
    const response = await api.getKnowledge()
    documents.value = response.documents
    categories.value = response.categories
    if (category.value && !response.categories.includes(category.value)) category.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法加载知识库。'
  } finally {
    loading.value = false
  }
}

async function addDocument() {
  if (!title.value.trim() || !content.value.trim() || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await api.addKnowledge({ title: title.value.trim(), content: content.value.trim(), category: category.value || '演示政策', source: '演示政策' })
    title.value = ''
    content.value = ''
    await loadDocuments()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '新增知识失败。'
  } finally {
    saving.value = false
  }
}

async function deleteDocument(document: KnowledgeDocument) {
  if (!window.confirm(`确定删除「${document.title}」？`)) return
  error.value = ''
  try {
    const result = await api.deleteKnowledge(document.id)
    if (!result.deleted) throw new Error('服务未确认删除该文档。')
    documents.value = documents.value.filter((item) => item.id !== document.id)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '删除知识失败。'
  }
}

async function searchKnowledge() {
  if (!query.value.trim() || searchLoading.value) return
  searchLoading.value = true
  searchDone.value = false
  searchError.value = ''
  try {
    const response = await api.search(query.value.trim(), searchDomain.value ? [searchDomain.value] : [], 8)
    searchResults.value = response.results
    searchMeta.value = { strategy: response.strategy, embedding_provider: response.embedding_provider, duration_ms: response.duration_ms }
    searchDone.value = true
  } catch (cause) {
    searchError.value = cause instanceof Error ? cause.message : '检索失败，请重试。'
  } finally {
    searchLoading.value = false
  }
}

onMounted(loadDocuments)
</script>

<template>
  <section data-page="knowledge">
    <div class="page-toolbar">
      <div class="toolbar-search"><Icon name="search" :size="16" /><input v-model="query" aria-label="搜索知识库" placeholder="搜索政策、商品或流程" @keydown.enter="searchKnowledge" /><button class="icon-button" aria-label="执行知识检索" :disabled="searchLoading || !query.trim()" @click="searchKnowledge"><span v-if="searchLoading" class="spinner"></span><Icon v-else name="arrow-up" :size="15" /></button></div>
      <select v-model="searchDomain" class="filter-select" aria-label="知识领域筛选"><option value="">全部领域</option><option v-for="item in categories" :key="item" :value="item">{{ item }}</option></select>
    </div>
    <div v-if="searchError" class="error-banner"><Icon name="alert" :size="15" />{{ searchError }}<button class="retry-link" @click="searchKnowledge">重试</button></div>
    <div v-if="searchDone" class="panel results-panel">
      <div class="panel-header"><div><div class="panel-title">检索结果</div><div class="panel-subtitle">{{ searchMeta?.strategy }} · {{ searchMeta?.embedding_provider }} · {{ searchMeta?.duration_ms }} ms</div></div><button class="link-button" @click="searchDone = false">收起</button></div>
      <div v-if="searchResults.length"><article v-for="result in searchResults" :key="result.id" class="search-result"><h3>{{ result.title }}</h3><p>{{ result.content }}</p><div class="result-meta"><span>{{ result.category }}</span><span>来源：{{ result.source || '演示政策' }}</span><span>综合分 {{ result.score.toFixed(3) }}</span><span>BM25 {{ result.bm25_score.toFixed(3) }}</span></div></article></div>
      <div v-else class="empty-state"><div><h3>没有匹配的知识</h3><p>服务未返回相关结果。可调整关键词后重新检索。</p></div></div>
    </div>
    <div class="knowledge-layout">
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">知识文档</div><div class="panel-subtitle">{{ filteredDocuments.length }} 项 · 由服务端读取</div></div><select v-model="category" class="filter-select" aria-label="按类别筛选文档"><option value="">全部类别</option><option v-for="item in categories" :key="item" :value="item">{{ item }}</option></select></div>
        <div v-if="loading" class="empty-state"><div class="loading-line"><span class="spinner"></span>正在加载知识文档…</div></div>
        <div v-else-if="error && documents.length === 0" class="empty-state"><div><div class="empty-icon"><Icon name="book" :size="21" /></div><h3>知识库暂不可用</h3><p>{{ error }}</p><button class="secondary-button" @click="loadDocuments"><Icon name="refresh" :size="14" />重试读取</button></div></div>
        <div v-else-if="filteredDocuments.length" class="document-list">
          <article v-for="document in filteredDocuments" :key="document.id" class="document-card">
            <div class="document-card-header"><h3>{{ document.title }}</h3><button class="icon-button" :aria-label="`删除 ${document.title}`" @click="deleteDocument(document)"><Icon name="trash" :size="15" /></button></div>
            <span class="pill">{{ document.category }}</span><p>{{ document.content }}</p>
            <div class="document-card-footer"><span>{{ document.source || '演示政策' }} · {{ document.version || '—' }}</span><time>{{ document.updated_at ? new Date(document.updated_at).toLocaleDateString('zh-CN') : '—' }}</time></div>
          </article>
        </div>
        <div v-else class="empty-state"><div><div class="empty-icon"><Icon name="book" :size="21" /></div><h3>{{ documents.length ? '没有符合条件的文档' : '知识库为空' }}</h3><p>{{ documents.length ? '调整类别筛选以查看其它资料。' : '添加资料后，可通过上方检索框调用演示服务进行搜索。' }}</p></div></div>
        <div v-if="error && documents.length" class="error-banner" style="margin: 12px">{{ error }}<button class="retry-link" @click="loadDocuments">重试</button></div>
      </section>
      <section class="panel form-panel">
        <div class="panel-header"><div><div class="panel-title">添加知识</div><div class="panel-subtitle">通过 API 提交新文档</div></div><span class="pill pill--muted">演示政策</span></div>
        <form class="form-body" @submit.prevent="addDocument">
          <div class="field"><label for="knowledge-title">文档标题</label><input id="knowledge-title" v-model="title" maxlength="120" placeholder="例如：退货申请说明" required /></div>
          <div class="field"><label for="knowledge-category">分类</label><input id="knowledge-category" v-model="category" maxlength="60" placeholder="政策 / 商品 / 流程" required /></div>
          <div class="field"><label for="knowledge-content">正文</label><textarea id="knowledge-content" v-model="content" maxlength="12000" placeholder="录入可被客服检索的资料…" required></textarea></div>
          <p class="form-note">资料来源标记为“演示政策”，不代表商家实际条款或承诺。</p>
          <button class="primary-button" type="submit" :disabled="saving || !title.trim() || !content.trim()"><span v-if="saving" class="spinner"></span><Icon v-else name="plus" :size="15" />{{ saving ? '正在提交…' : '保存文档' }}</button>
          <div v-if="error && documents.length" class="inline-error" role="alert">{{ error }}</div>
        </form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.form-note { margin: 0; color: var(--muted-2); font-size: 10px; line-height: 1.6; }
.form-body > .primary-button { width: 100%; }
@media (max-width: 650px) { .page-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) auto; }.toolbar-search { grid-column: 1 / -1; } }
</style>
