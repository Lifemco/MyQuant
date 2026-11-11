<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { MinuteData, MinutePoint } from '@/types'
import { computeMACD } from '@/utils/indicator'
import type { MacdResult } from '@/utils/indicator'

/** 同花顺式分时图:价格+均价(主图,时间轴紧贴其下)/ 分时量 / MACDFS */
const props = defineProps<{ data: MinuteData }>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const COLOR_UP = '#ef5350'
const COLOR_DOWN = '#26a69a'
// 副图标题样式:深色加粗,更醒目
const TITLE_STYLE = { fontSize: 12, color: '#303133', fontWeight: 'bold' as const }

// 最近一次渲染的计算缓存,供悬停时更新副图标题数值
let cached: { points: MinutePoint[]; macd: MacdResult } | null = null

function fmtVol(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`
  return v.toFixed(0)
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined ? '--' : v.toFixed(digits)
}

/** 副图标题:图内左上角,展示指定分钟位置的指标值(悬停联动) */
function buildTitles(idx: number): echarts.TitleComponentOption[] {
  if (!cached) return []
  const { points, macd } = cached
  const i = Math.max(0, Math.min(idx, points.length - 1))
  return [
    {
      text: `分时量  ${fmtVol(points[i].volume)}`,
      left: 64,
      top: '53.5%',
      textStyle: TITLE_STYLE,
    },
    {
      // 分钟级 MACD 数值量级小,显示三位小数
      text: `MACDFS(12,26,9)  DIF ${fmtNum(macd.dif[i], 3)}  DEA ${fmtNum(macd.dea[i], 3)}  MACD ${fmtNum(macd.macd[i], 3)}`,
      left: 64,
      top: '80%',
      textStyle: TITLE_STYLE,
    },
  ]
}

/** 固定刻度:开盘、午休前最后一分钟、收盘(自动适配港股 12:00/16:00) */
function computeFixedTicks(times: string[]): Set<string> {
  if (times.length === 0) return new Set()
  const toMin = (t: string): number => parseInt(t.slice(0, 2)) * 60 + parseInt(t.slice(3))
  let morningEnd = times.length - 1
  // 相邻两点间隔超过 1 分钟即为午休断点
  for (let i = 1; i < times.length; i++) {
    if (toMin(times[i]) - toMin(times[i - 1]) > 1) {
      morningEnd = i - 1
      break
    }
  }
  return new Set([times[0], times[morningEnd], times[times.length - 1]])
}

function buildOption(): echarts.EChartsOption {
  const points = props.data.points
  const times = points.map((p) => p.time)
  const prices = points.map((p) => p.price)
  const avgs = points.map((p) => p.avg)
  const prevClose = props.data.prevClose
  const fixedTicks = computeFixedTicks(times)

  // 价格线:黑色;均价线保持黄色不变
  const lineColor = '#1a1a1a'

  // Y 轴范围:以昨收为中心对称展开
  let min = Math.min(...prices, ...(prevClose ? [prevClose] : []))
  let max = Math.max(...prices, ...(prevClose ? [prevClose] : []))
  if (prevClose) {
    const half = Math.max(max - prevClose, prevClose - min, prevClose * 0.002)
    min = prevClose - half
    max = prevClose + half
  }

  const volumes = points.map((p, i) => {
    const prev = i > 0 ? points[i - 1].price : (prevClose ?? p.price)
    return {
      value: p.volume,
      itemStyle: { color: p.price >= prev ? COLOR_UP : COLOR_DOWN },
    }
  })

  // MACDFS:分钟价格序列上计算 MACD
  const macd = computeMACD(prices)
  const macdBars = macd.macd.map((v) => ({
    value: v,
    itemStyle: { color: (v ?? 0) >= 0 ? COLOR_UP : COLOR_DOWN },
  }))
  // 缓存供悬停联动
  cached = { points, macd }

  return {
    animation: false,
    // 副图标题:图内左上角显示最新值,悬停时联动更新
    title: buildTitles(points.length - 1),
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] },
      textStyle: { fontSize: 11 },
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e4e7ed',
      extraCssText: 'box-shadow: 0 2px 8px rgba(0,0,0,0.12); padding: 6px 8px;',
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    // 三段式:分时价 42%(时间轴紧贴其下)/ 分时量 / MACDFS 各 20.5%,段间空隙 ~5.5%;
    // 每个图带边框便于区分
    grid: [
      { left: 56, right: 16, top: 16, height: '42%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '53%', height: '20.5%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '79.5%', height: '20.5%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
    ],
    // 分时图禁用缩放/平移(日线/周线/月线保留缩放)
    xAxis: [0, 1, 2].map((i) => ({
      type: 'category' as const,
      data: times,
      gridIndex: i,
      // 必须为 true:柱图所在轴会被强制 boundaryGap=true,
      // 若价格线轴为 false 会导致主图与副图 X 轴两端错位
      boundaryGap: true,
      axisTick: { show: false },
      axisLine: { show: i === 0 },
      // 时间轴紧贴分时价图下方,只显示固定刻度(开盘/午休/收盘)
      axisLabel:
        i === 0
          ? {
              fontSize: 10,
              interval: 0,
              formatter: (val: string) => (fixedTicks.has(val) ? val : ''),
            }
          : { show: false },
    })),
    yAxis: [
      {
        scale: false,
        min,
        max,
        gridIndex: 0,
        splitNumber: 6,
        axisLabel: {
          fontSize: 10,
          // 价格标签保留两位小数
          formatter: (v: number) => v.toFixed(2),
          // 相对昨收定红绿
          color: (v?: string | number) => {
            const num = typeof v === 'string' ? parseFloat(v) : (v ?? 0)
            if (!prevClose) return '#666'
            return num > prevClose ? COLOR_UP : num < prevClose ? COLOR_DOWN : '#666'
          },
        },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: {
          fontSize: 10,
          formatter: (v: number) => (v >= 1e4 ? `${(v / 1e4).toFixed(0)}万` : String(v)),
        },
      },
      { scale: true, gridIndex: 2, splitNumber: 2, axisLabel: { fontSize: 10 } },
    ],
    series: [
      {
        name: '价格',
        type: 'line',
        data: prices,
        showSymbol: false,
        lineStyle: { width: 1.5, color: lineColor },
        areaStyle: { opacity: 0.08, color: '#9e9e9e' },
        xAxisIndex: 0,
        yAxisIndex: 0,
        markLine: prevClose
          ? {
              silent: true,
              symbol: 'none',
              data: [{ yAxis: prevClose }],
              lineStyle: { color: '#999', type: 'dashed', width: 1 },
              label: { show: false },
            }
          : undefined,
      },
      {
        name: '均价',
        type: 'line',
        data: avgs,
        showSymbol: false,
        lineStyle: { width: 1, color: '#ff9800' },
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      {
        name: '分时量',
        type: 'bar',
        data: volumes,
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
      {
        name: 'MACD',
        type: 'bar',
        data: macdBars,
        xAxisIndex: 2,
        yAxisIndex: 2,
      },
      {
        name: 'DIF',
        type: 'line',
        data: macd.dif,
        showSymbol: false,
        lineStyle: { width: 1, color: '#ff9800' },
        xAxisIndex: 2,
        yAxisIndex: 2,
      },
      {
        name: 'DEA',
        type: 'line',
        data: macd.dea,
        showSymbol: false,
        lineStyle: { width: 1, color: '#2196f3' },
        xAxisIndex: 2,
        yAxisIndex: 2,
      },
    ] as echarts.SeriesOption[],
  }
}

function render(): void {
  if (!chart || props.data.points.length === 0) return
  chart.setOption(buildOption(), { notMerge: true })
}

function handleResize(): void {
  chart?.resize()
}

// 容器尺寸变化(窗口缩放、侧栏折叠、分隔条拖拽)时自动 resize
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (chartEl.value) {
    chart = echarts.init(chartEl.value)
    render()
    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(chartEl.value)
    // 悬停十字光标移动 → 副图标题联动显示该分钟的指标值
    chart.on('updateAxisPointer', (event) => {
      const idx = (event as { dataIndexInside?: number }).dataIndexInside
      if (idx === undefined || idx < 0 || !cached) return
      chart?.setOption({ title: buildTitles(idx) })
    })
  }
})

watch(() => props.data, render, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartEl" class="h-full w-full" />
</template>
