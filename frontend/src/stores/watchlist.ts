import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getQuotes } from '@/api/monitor'
import { getOverview, refreshOverview } from '@/api/watchlist'
import type { Market, QuoteSnapshot, WatchOverviewItem } from '@/types'

/** 自选监控状态:列表、选中项、行情快照(3s 轮询)、信号低频刷新 */
export const useWatchlistStore = defineStore('watchlist', () => {
  const items = ref<WatchOverviewItem[]>([])
  const loading = ref(false)
  const refreshing = ref(false)
  const selectedKey = ref<string>('')
  /** 实时快照,key 为 market/symbol */
  const quotes = ref<Record<string, QuoteSnapshot>>({})

  const selected = computed<WatchOverviewItem | null>(
    () => items.value.find((i) => keyOf(i.market, i.symbol) === selectedKey.value) ?? null,
  )

  const selectedQuote = computed<QuoteSnapshot | null>(() =>
    selectedKey.value ? (quotes.value[selectedKey.value] ?? null) : null,
  )

  function keyOf(market: Market | string, symbol: string): string {
    return `${market}/${symbol}`
  }

  function quoteOf(market: Market | string, symbol: string): QuoteSnapshot | null {
    return quotes.value[keyOf(market, symbol)] ?? null
  }

  function select(market: Market | string, symbol: string): void {
    selectedKey.value = keyOf(market, symbol)
  }

  /** 加载总览(只读缓存,不抓行情) */
  async function load(): Promise<void> {
    loading.value = true
    try {
      items.value = await getOverview()
      if (!selectedKey.value && items.value.length > 0) {
        selectedKey.value = keyOf(items.value[0].market, items.value[0].symbol)
      }
    } finally {
      loading.value = false
    }
  }

  /** 刷新行情(抓取最新K线并重算信号) */
  async function refresh(): Promise<void> {
    refreshing.value = true
    try {
      items.value = await refreshOverview()
    } finally {
      refreshing.value = false
    }
  }

  /** 3s 轮询:批量快照,只更新价格相关字段,不重算信号 */
  async function pollQuotes(): Promise<void> {
    if (items.value.length === 0) return
    try {
      const snapshots = await getQuotes(
        items.value.map((i) => ({ market: i.market, symbol: i.symbol })),
      )
      const map: Record<string, QuoteSnapshot> = {}
      for (const q of snapshots) {
        map[keyOf(q.market, q.symbol)] = q
      }
      quotes.value = map
    } catch {
      // 轮询失败静默,下个周期重试
    }
  }

  return {
    items,
    loading,
    refreshing,
    selectedKey,
    selected,
    quotes,
    selectedQuote,
    keyOf,
    quoteOf,
    select,
    load,
    refresh,
    pollQuotes,
  }
})
