<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { EquityPoint } from '@/types'

const props = defineProps<{ equityCurve: EquityPoint[] }>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function render(): void {
  if (!chart || props.equityCurve.length === 0) return
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, top: 30, bottom: 60 },
    xAxis: { type: 'category', data: props.equityCurve.map((p) => p.date) },
    yAxis: { scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 10 }],
    series: [
      {
        type: 'line',
        name: '净值',
        data: props.equityCurve.map((p) => p.equity),
        showSymbol: false,
        lineStyle: { width: 2, color: '#409eff' },
        areaStyle: { opacity: 0.08 },
      },
    ],
  })
}

onMounted(() => {
  if (chartEl.value) {
    chart = echarts.init(chartEl.value)
    render()
  }
})

watch(() => props.equityCurve, render, { deep: true })

onBeforeUnmount(() => {
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartEl" class="h-80 w-full" />
</template>
