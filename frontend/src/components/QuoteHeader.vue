<script setup lang="ts">
import { computed } from 'vue'

import type { MarketDataInfo, QuoteSnapshot, WatchOverviewItem } from '@/types'

/** 同花顺式行情面板:大字价格 + 涨跌 + 完整行情字段网格 */
const props = defineProps<{
  item: WatchOverviewItem
  quote: QuoteSnapshot | null
  dataInfo?: MarketDataInfo | null
}>()

/** 现价/涨跌幅优先取实时快照,快照缺失回落到K线收盘 */
const price = computed(() => props.quote?.price ?? props.item.close)
const changePct = computed(() => props.quote?.changePct ?? props.item.changePct)
const change = computed(() => {
  if (props.quote?.change !== null && props.quote?.change !== undefined) return props.quote.change
  if (price.value !== null && props.quote?.prevClose) return price.value - props.quote.prevClose
  return null
})

const info = computed(() => props.dataInfo ?? props.item.dataInfo)
const volumeUnit = computed(() =>
  props.quote?.volumeUnit === 'lot100'
    ? '手'
    : props.quote?.volumeUnit === 'share'
      ? '股'
      : '单位未知',
)
const dataDescription = computed(() => {
  const data = info.value
  if (!data) return 'K线来源、复权与单位未确认，请刷新后核对'
  const sources: Record<string, string> = {
    tencent: '腾讯',
    yahoo: 'Yahoo',
    eastmoney: '东方财富',
    baostock: 'BaoStock',
  }
  const adjustments: Record<string, string> = {
    none: '不复权',
    qfq: '前复权',
    hfq: '后复权',
    yahoo_auto_adjust: 'Yahoo调整价',
  }
  return `K线：${sources[data.source] ?? data.source} · ${adjustments[data.adjustment]} · 成交量${data.volumeUnit === 'lot100' ? '手' : '股'}${data.priceUnit === 'point' ? ' · 价格为指数点位' : ''}`
})

const isUp = computed(() => (changePct.value ?? 0) >= 0)
const trendClass = computed(() => (isUp.value ? 'text-red-500' : 'text-green-600'))

function fmt(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined ? '--' : v.toFixed(digits)
}

function fmtAmount(v: number | null | undefined): string {
  if (v === null || v === undefined) return '--'
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}万`
  return v.toFixed(0)
}

function fmtVolume(v: number | null | undefined): string {
  if (v === null || v === undefined) return '--'
  // 数值保留原单位，单位由提供器明确声明后显示。
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(1)}万`
  return String(v)
}

/** 行情字段网格(同花顺面板布局) */
const fields = computed(() => [
  { label: '今开', value: fmt(props.quote?.open), trend: compareWith(props.quote?.open) },
  { label: '昨收', value: fmt(props.quote?.prevClose), trend: '' },
  { label: '最高', value: fmt(props.quote?.high), trend: 'text-red-500' },
  { label: '最低', value: fmt(props.quote?.low), trend: 'text-green-600' },
  {
    label: '换手率',
    value: props.quote?.turnoverRate != null ? `${fmt(props.quote.turnoverRate)}%` : '--',
    trend: '',
  },
  { label: `成交量(${volumeUnit.value})`, value: fmtVolume(props.quote?.volume), trend: '' },
  { label: '成交额', value: fmtAmount(props.quote?.amount), trend: '' },
  {
    label: '振幅',
    value: props.quote?.amplitude != null ? `${fmt(props.quote.amplitude)}%` : '--',
    trend: '',
  },
  { label: '市盈率', value: fmt(props.quote?.peRatio), trend: '' },
  { label: '市净率', value: fmt(props.quote?.pbRatio), trend: '' },
  {
    label: '总市值',
    value: props.quote?.totalMarketCap != null ? `${fmt(props.quote.totalMarketCap)}亿` : '--',
    trend: '',
  },
  {
    label: '流通市值',
    value:
      props.quote?.circulatingMarketCap != null
        ? `${fmt(props.quote.circulatingMarketCap)}亿`
        : '--',
    trend: '',
  },
])

/** 快照时间格式化:'20260930150527' → '2026-09-30 15:05:27';港股原样截取 */
function formatQuoteTime(t: string): string {
  if (/^\d{14}$/.test(t)) {
    return `${t.slice(0, 4)}-${t.slice(4, 6)}-${t.slice(6, 8)} ${t.slice(8, 10)}:${t.slice(10, 12)}:${t.slice(12, 14)}`
  }
  return t
}

/** 与昨收比较定红绿 */
function compareWith(v: number | null | undefined): string {
  if (v == null || props.quote?.prevClose == null) return ''
  if (v > props.quote.prevClose) return 'text-red-500'
  if (v < props.quote.prevClose) return 'text-green-600'
  return ''
}
</script>

<template>
  <div class="quote-header rounded-lg border border-gray-200 bg-white px-4 py-3">
    <div class="quote-layout flex items-stretch gap-6">
      <!-- 左:名称 + 大字价格 -->
      <div class="flex min-w-44 flex-col justify-center">
        <div class="flex items-baseline gap-2">
          <span class="text-lg font-bold text-gray-800">{{ item.name }}</span>
          <span class="text-xs text-gray-400">
            {{ item.market.toUpperCase() }} {{ item.symbol }}
          </span>
        </div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-3xl font-bold" :class="trendClass">{{ fmt(price) }}</span>
          <span class="text-sm font-medium" :class="trendClass">
            {{
              change !== null && change !== undefined
                ? (change >= 0 ? '+' : '') + fmt(change)
                : '--'
            }}
          </span>
          <span class="text-sm font-medium" :class="trendClass">
            {{
              changePct !== null && changePct !== undefined
                ? (changePct >= 0 ? '+' : '') + (changePct * 100).toFixed(2) + '%'
                : '--'
            }}
          </span>
        </div>
        <div class="mt-1 text-xs text-gray-400">
          {{
            quote?.time
              ? `更新 ${formatQuoteTime(quote.time)}`
              : `缓存收盘价 · ${item.dataAsOf ?? '日期未知'}`
          }}
          <span v-if="item.market === 'us'">（美股仅日线，手动刷新）</span>
          <div data-testid="data-convention">{{ dataDescription }}</div>
          <div v-if="item.refreshError || item.error" class="text-amber-600">
            {{ item.refreshError || item.error }}
          </div>
        </div>
      </div>

      <!-- 右:行情字段网格 -->
      <div
        class="quote-fields grid flex-1 grid-cols-4 content-center gap-x-6 gap-y-1.5 border-l border-gray-100 pl-6 text-sm"
      >
        <div v-for="f in fields" :key="f.label" class="flex justify-between">
          <span class="text-gray-400">{{ f.label }}</span>
          <span class="font-medium" :class="f.trend || 'text-gray-700'">{{ f.value }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quote-fields > div {
  gap: 10px;
  min-width: 0;
  white-space: nowrap;
}
@media (max-width: 1250px) {
  .quote-layout {
    flex-direction: column;
    gap: 12px;
  }
  .quote-fields {
    border-left: 0;
    padding-left: 0;
    column-gap: 16px;
    font-size: 12px;
  }
}
@media (max-width: 760px) {
  .quote-header {
    padding: 12px;
  }
  .quote-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    font-size: 11px;
    gap: 7px 14px;
  }
  .quote-layout {
    gap: 14px;
  }
}
</style>
