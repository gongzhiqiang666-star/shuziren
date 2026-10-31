<script setup lang="ts">
import { ref } from 'vue'
import type { ApiClient } from '../api'
import type { NoticeSink, Product, Session } from '../types'
import DiagnosticsPanel from './DiagnosticsPanel.vue'
import EventsPanel from './EventsPanel.vue'
import PlatformPanel from './PlatformPanel.vue'
defineProps<{ api: ApiClient; shopId: string; products: Product[]; sessions: Session[]; reload: () => Promise<void>; notify: NoticeSink }>()
const tab = ref('diagnostics')
</script>
<template>
  <div class="page-heading"><div><div class="eyebrow">LOCAL TEST & TAOBAO</div><h1>联调与淘宝</h1><p>从本地检索、评论回放，到获准的平台接口逐项核验。</p></div></div><div class="integration-tabs segmented"><button :class="{ active: tab === 'diagnostics' }" @click="tab = 'diagnostics'">诊断与检索</button><button :class="{ active: tab === 'events' }" @click="tab = 'events'">场次绑定与评论</button><button :class="{ active: tab === 'platform' }" @click="tab = 'platform'">商品与平台操作</button></div>
  <div v-show="tab === 'diagnostics'"><DiagnosticsPanel :api="api" :shop-id="shopId" :products="products" :sessions="sessions" /></div>
  <div v-show="tab === 'events'"><EventsPanel :api="api" :shop-id="shopId" :products="products" :sessions="sessions" :reload="reload" :notify="notify" /></div>
  <div v-show="tab === 'platform'"><PlatformPanel :api="api" :shop-id="shopId" :products="products" :sessions="sessions" :reload="reload" :notify="notify" /></div>
</template>
