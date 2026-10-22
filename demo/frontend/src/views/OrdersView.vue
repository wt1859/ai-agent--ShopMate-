<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { api } from '../api'
import type { Order, Product } from '../types'

const activeTab = ref<'orders' | 'products'>('orders')
const orders = ref<Order[]>([])
const products = ref<Product[]>([])
const ordersLoading = ref(false)
const productsLoading = ref(false)
const ordersError = ref('')
const productsError = ref('')
const orderQuery = ref('')

const filteredOrders = computed(() => orders.value.filter((order) => [order.order_no, order.product_name, order.sku, order.tracking_no].join(' ').toLowerCase().includes(orderQuery.value.trim().toLowerCase())))

async function loadOrders() {
  ordersLoading.value = true
  ordersError.value = ''
  try { orders.value = (await api.getOrders()).orders }
  catch (error) { ordersError.value = error instanceof Error ? error.message : '订单数据暂不可用。' }
  finally { ordersLoading.value = false }
}

async function loadProducts() {
  productsLoading.value = true
  productsError.value = ''
  try { products.value = (await api.getProducts()).products }
  catch (error) { productsError.value = error instanceof Error ? error.message : '商品数据暂不可用。' }
  finally { productsLoading.value = false }
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

function stockClass(stock: number) { return stock <= 0 ? 'stock-empty' : stock <= 5 ? 'stock-low' : '' }
function stockLabel(stock: number) { return stock <= 0 ? '缺货' : stock <= 5 ? `库存 ${stock}` : `库存 ${stock}` }

onMounted(() => { void loadOrders(); void loadProducts() })
</script>

<template>
  <section data-page="orders">
    <div class="operations-tabs" role="tablist" aria-label="数据类型">
      <button class="tab-button" :class="{ 'tab-button--active': activeTab === 'orders' }" role="tab" :aria-selected="activeTab === 'orders'" @click="activeTab = 'orders'">订单</button>
      <button class="tab-button" :class="{ 'tab-button--active': activeTab === 'products' }" role="tab" :aria-selected="activeTab === 'products'" @click="activeTab = 'products'">商品</button>
    </div>
    <template v-if="activeTab === 'orders'">
      <div class="page-toolbar"><div class="toolbar-search"><Icon name="search" :size="16" /><input v-model="orderQuery" aria-label="搜索订单" placeholder="搜索订单号、商品、SKU 或物流单号" /></div><button class="secondary-button" :disabled="ordersLoading" @click="loadOrders"><Icon name="refresh" :size="15" />刷新数据</button></div>
      <div v-if="ordersError" class="error-banner"><Icon name="alert" :size="15" />{{ ordersError }}<button class="retry-link" @click="loadOrders">重试</button></div>
      <div class="panel table-panel">
        <div class="panel-header"><div><div class="panel-title">订单列表</div><div class="panel-subtitle">{{ orders.length }} 笔 · 服务端演示数据</div></div><span class="pill pill--muted">订单操作需客户服务响应授权</span></div>
        <div v-if="ordersLoading" class="empty-state"><div class="loading-line"><span class="spinner"></span>正在读取订单…</div></div>
        <div v-else-if="ordersError && !orders.length" class="empty-state"><div><div class="empty-icon"><Icon name="box" :size="21" /></div><h3>订单数据暂不可用</h3><p>{{ ordersError }}</p><button class="secondary-button" @click="loadOrders"><Icon name="refresh" :size="14" />重试</button></div></div>
        <div v-else-if="filteredOrders.length" class="table-wrap"><table class="data-table"><thead><tr><th>订单信息</th><th>商品</th><th>状态</th><th>数量 / 金额</th><th>物流单号</th><th>更新时间</th></tr></thead><tbody><tr v-for="order in filteredOrders" :key="order.order_no"><td><strong>{{ order.order_no }}</strong></td><td><strong>{{ order.product_name }}</strong><span class="table-secondary">{{ order.sku }}</span></td><td><span class="pill" :class="order.status === 'cancelled' ? 'pill--red' : order.status === 'pending' ? 'pill--amber' : 'pill--muted'">{{ order.status_label || order.status }}</span></td><td><strong>{{ order.quantity }} 件</strong><span class="table-secondary amount">¥{{ order.total_amount.toFixed(2) }}</span></td><td><span class="amount">{{ order.tracking_no || '—' }}</span></td><td>{{ formatTime(order.updated_at) }}</td></tr></tbody></table></div>
        <div v-else class="empty-state"><div><div class="empty-icon"><Icon name="search" :size="21" /></div><h3>{{ orders.length ? '没有匹配订单' : '暂无订单' }}</h3><p>{{ orders.length ? '试试其它订单号、商品名或 SKU。' : '服务未返回订单数据，不会显示模拟订单。' }}</p></div></div>
      </div>
    </template>
    <template v-else>
      <div class="page-toolbar"><div class="toolbar-search"><Icon name="search" :size="16" /><input aria-label="商品列表说明" readonly placeholder="商品数据来自演示服务" /></div><button class="secondary-button" :disabled="productsLoading" @click="loadProducts"><Icon name="refresh" :size="15" />刷新数据</button></div>
      <div v-if="productsError" class="error-banner"><Icon name="alert" :size="15" />{{ productsError }}<button class="retry-link" @click="loadProducts">重试</button></div>
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">商品目录</div><div class="panel-subtitle">{{ products.length }} 项 · 库存与售价以服务端数据为准</div></div><span class="pill pill--muted">演示数据</span></div>
        <div v-if="productsLoading" class="empty-state"><div class="loading-line"><span class="spinner"></span>正在读取商品…</div></div>
        <div v-else-if="productsError && !products.length" class="empty-state"><div><div class="empty-icon"><Icon name="box" :size="21" /></div><h3>商品目录暂不可用</h3><p>{{ productsError }}</p><button class="secondary-button" @click="loadProducts"><Icon name="refresh" :size="14" />重试</button></div></div>
        <div v-else-if="products.length" class="product-grid"><article v-for="product in products" :key="product.sku" class="product-card"><div class="document-card-header"><span class="pill pill--muted">{{ product.category }}</span><span :class="stockClass(product.stock)">{{ stockLabel(product.stock) }}</span></div><h3>{{ product.name }}</h3><p>{{ product.description }}</p><div class="product-meta"><span class="product-price">¥{{ product.price.toFixed(2) }}</span><span>{{ product.sku }}</span></div></article></div>
        <div v-else class="empty-state"><div><div class="empty-icon"><Icon name="box" :size="21" /></div><h3>暂无商品</h3><p>演示服务当前未返回商品目录。</p></div></div>
      </section>
    </template>
  </section>
</template>
