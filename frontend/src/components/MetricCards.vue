<script setup lang="ts">
import { computed } from 'vue'

import type { BacktestMetrics } from '@/types'

const props = defineProps<{ metrics: BacktestMetrics }>()

interface MetricItem {
  label: string
  value: string
  negative: boolean
}

function fmtPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

const items = computed<MetricItem[]>(() => [
  {
    label: '总收益率',
    value: fmtPct(props.metrics.totalReturn),
    negative: props.metrics.totalReturn < 0,
  },
  {
    label: '年化收益',
    value: fmtPct(props.metrics.annualReturn),
    negative: props.metrics.annualReturn < 0,
  },
  { label: '年化波动', value: fmtPct(props.metrics.annualVolatility), negative: false },
  {
    label: '夏普比率',
    value: props.metrics.sharpeRatio.toFixed(2),
    negative: props.metrics.sharpeRatio < 0,
  },
  { label: '最大回撤', value: fmtPct(props.metrics.maxDrawdown), negative: true },
  {
    label: '卡玛比率',
    value: props.metrics.calmarRatio.toFixed(2),
    negative: props.metrics.calmarRatio < 0,
  },
  { label: '交易次数', value: String(props.metrics.totalTrades), negative: false },
  { label: '胜率', value: fmtPct(props.metrics.winRate), negative: false },
])
</script>

<template>
  <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
    <div
      v-for="item in items"
      :key="item.label"
      class="rounded-lg border border-gray-200 bg-white p-4"
    >
      <div class="text-xs text-gray-500">{{ item.label }}</div>
      <div
        class="mt-1 text-xl font-semibold"
        :class="item.negative ? 'text-green-600' : 'text-red-500'"
      >
        {{ item.value }}
      </div>
    </div>
  </div>
</template>
