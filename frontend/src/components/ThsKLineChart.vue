<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { BarPoint, SignalMarker } from '@/types'
import { computeKDJ, computeMACD, computeMA } from '@/utils/indicator'
import type { KdjResult, MacdResult } from '@/utils/indicator'

const props = defineProps<{ bars: BarPoint[]; markers: SignalMarker[] }>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

// 同花顺风格配色:红涨绿跌
const COLOR_UP = '#ef5350'
const COLOR_DOWN = '#26a69a'
const MA_COLORS = { ma5: '#ff9800', ma10: '#2196f3', ma20: '#9c27b0', ma60: '#607d8b' }
// 副图标题样式:深色加粗,更醒目
const TITLE_STYLE = { fontSize: 12, color: '#303133', fontWeight: 'bold' as const }

// 最近一次渲染的计算缓存,供悬停时更新副图标题数值
let cached: { bars: BarPoint[]; macd: MacdResult; kdj: KdjResult } | null = null

function fmtVol(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`
  return v.toFixed(0)
}

function fmtNum(v: number | null | undefined): string {
  return v === null || v === undefined ? '--' : v.toFixed(2)
}

/** 副图标题:图内左上角,展示指定K线位置的指标值(同花顺交互) */
function buildTitles(idx: number): echarts.TitleComponentOption[] {
  if (!cached) return []
  const { bars, macd, kdj } = cached
  const i = Math.max(0, Math.min(idx, bars.length - 1))
  const bar = bars[i]
  return [
    { text: `成交量  ${fmtVol(bar.volume)}`, left: 64, top: '30.5%', textStyle: TITLE_STYLE },
    {
      text: `MACD(12,26,9)  DIF ${fmtNum(macd.dif[i])}  DEA ${fmtNum(macd.dea[i])}  MACD ${fmtNum(macd.macd[i])}`,
      left: 64,
      top: '56%',
      textStyle: TITLE_STYLE,
    },
    {
      text: `KDJ(9,3,3)  K ${fmtNum(kdj.k[i])}  D ${fmtNum(kdj.d[i])}  J ${fmtNum(kdj.j[i])}`,
      left: 64,
      top: '81.5%',
      textStyle: TITLE_STYLE,
    },
  ]
}

/** 紧凑中文 tooltip:限制在图表区域内,避免被遮挡 */
function buildTooltipFormatter(dates: string[], bars: BarPoint[]) {
  return (params: unknown): string => {
    const list = params as { seriesName: string; data: unknown; axisValue?: string }[]
    if (!list.length) return ''
    const axisValue = list[0].axisValue ?? ''
    const bar = bars.find((b) => b.date === axisValue)
    if (!bar) return ''

    const byName = new Map<string, unknown>()
    for (const p of list) byName.set(p.seriesName, p.data)

    const prevClose = bars[dates.indexOf(bar.date) - 1]?.close
    const changePct =
      prevClose && prevClose !== 0 ? ((bar.close - prevClose) / prevClose) * 100 : null
    const pctText = changePct === null ? '--' : `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%`
    const pctColor = changePct === null ? '#666' : changePct >= 0 ? COLOR_UP : COLOR_DOWN

    const maVal = (name: string) => {
      const v = byName.get(name)
      return typeof v === 'number' ? v.toFixed(2) : '--'
    }

    return [
      `<b>${bar.date}</b>`,
      `开 ${bar.open.toFixed(2)}&nbsp;&nbsp;收 ${bar.close.toFixed(2)}`,
      `高 ${bar.high.toFixed(2)}&nbsp;&nbsp;低 ${bar.low.toFixed(2)}`,
      `<span style="color:${pctColor}">涨跌 ${pctText}</span>&nbsp;&nbsp;量 ${fmtVol(bar.volume)}`,
      `<span style="color:${MA_COLORS.ma5}">MA5 ${maVal('MA5')}</span>&nbsp;<span style="color:${MA_COLORS.ma10}">MA10 ${maVal('MA10')}</span>`,
      `<span style="color:${MA_COLORS.ma20}">MA20 ${maVal('MA20')}</span>&nbsp;<span style="color:${MA_COLORS.ma60}">MA60 ${maVal('MA60')}</span>`,
    ].join('<br/>')
  }
}

function buildOption(): echarts.EChartsOption {
  const bars = props.bars
  const dates = bars.map((b) => b.date)
  const closes = bars.map((b) => b.close)
  const highs = bars.map((b) => b.high)
  const lows = bars.map((b) => b.low)
  // ECharts K线数据顺序: [open, close, low, high]
  const klineData = bars.map((b) => [b.open, b.close, b.low, b.high])
  // 成交量柱颜色跟随阴阳
  const volumeData = bars.map((b) => ({
    value: b.volume,
    itemStyle: { color: b.close >= b.open ? COLOR_UP : COLOR_DOWN },
  }))
  const macd = computeMACD(closes)
  const macdBars = macd.macd.map((v) => ({
    value: v,
    itemStyle: { color: (v ?? 0) >= 0 ? COLOR_UP : COLOR_DOWN },
  }))
  const kdj = computeKDJ(highs, lows, closes)
  // 缓存供悬停联动
  cached = { bars, macd, kdj }

  // 买卖点 → 散点:B 在最低价下方红色,S 在最高价上方绿色
  const dateIndex = new Map(dates.map((d, i) => [d, i]))
  const buyPoints = props.markers
    .filter((m) => m.type === 'buy')
    .map((m) => {
      const bar = bars[dateIndex.get(m.date) ?? -1]
      return { value: [m.date, bar ? bar.low * 0.98 : m.price], price: m.price }
    })
  const sellPoints = props.markers
    .filter((m) => m.type === 'sell')
    .map((m) => {
      const bar = bars[dateIndex.get(m.date) ?? -1]
      return { value: [m.date, bar ? bar.high * 1.02 : m.price], price: m.price }
    })

  const maSeries: echarts.SeriesOption[] = ([5, 10, 20, 60] as const).map((w) => ({
    name: `MA${w}`,
    type: 'line' as const,
    // color 需设在系列级,否则图例图标颜色与均线不一致
    color: MA_COLORS[`ma${w}` as keyof typeof MA_COLORS],
    data: computeMA(closes, w),
    smooth: true,
    showSymbol: false,
    lineStyle: { width: 1 },
    xAxisIndex: 0,
    yAxisIndex: 0,
  }))

  const subAxisLabel = { fontSize: 10 }

  return {
    animation: false,
    legend: {
      data: ['MA5', 'MA10', 'MA20', 'MA60'],
      top: 2,
      textStyle: { fontSize: 11 },
    },
    // 副图标题初始显示最新一根的值,悬停时联动更新
    title: buildTitles(bars.length - 1),
    tooltip: {
      trigger: 'axis',
      // 限制在图表区域内,避免浮动窗被遮挡
      confine: true,
      axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] },
      formatter: buildTooltipFormatter(dates, bars),
      textStyle: { fontSize: 11 },
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e4e7ed',
      extraCssText: 'box-shadow: 0 2px 8px rgba(0,0,0,0.12); padding: 6px 8px;',
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    // 四段式:K线 17.5%(时间轴紧贴其下)/ 三副图各 ~20%,段间空隙 ~5.5%;
    // 每个图带边框(show+borderColor)便于区分
    grid: [
      { left: 56, right: 16, top: 30, height: '17.5%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '30%', height: '20%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '55.5%', height: '20%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '81%', height: '19%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
    ],
    xAxis: [0, 1, 2, 3].map((i) => ({
      type: 'category' as const,
      data: dates,
      gridIndex: i,
      boundaryGap: true,
      // 时间轴只显示在K线图正下方;首尾标签强制显示且向内对齐
      // (showMaxLabel 不配 alignMaxLabel 会让 ECharts 为容纳标签压缩 grid0 宽度,导致四图不对齐)
      axisLabel: {
        show: i === 0,
        fontSize: 10,
        hideOverlap: true,
        margin: 4,
        showMinLabel: true,
        showMaxLabel: true,
        alignMinLabel: 'left' as const,
        alignMaxLabel: 'right' as const,
      },
      axisTick: { show: false },
      axisLine: { show: i === 0 },
    })),
    yAxis: [
      { scale: true, gridIndex: 0, splitNumber: 4, axisLabel: subAxisLabel },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: {
          ...subAxisLabel,
          formatter: (v: number) =>
            v >= 1e8 ? `${(v / 1e8).toFixed(1)}亿` : `${(v / 1e4).toFixed(0)}万`,
        },
      },
      { scale: true, gridIndex: 2, splitNumber: 2, axisLabel: subAxisLabel },
      { scale: true, gridIndex: 3, splitNumber: 2, axisLabel: subAxisLabel },
    ],
    // 初始全部展示;滚轮/捏合纵向 = 以鼠标为中心缩放,触控板横向滑动 = 平移
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1, 2, 3],
        start: 0,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseWheel: true,
      },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: klineData,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: COLOR_UP, // 阳线填充(红)
          color0: COLOR_DOWN, // 阴线填充(绿)
          borderColor: COLOR_UP,
          borderColor0: COLOR_DOWN,
        },
      },
      ...maSeries,
      {
        name: '成交量',
        type: 'bar',
        data: volumeData,
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
      {
        name: 'K',
        type: 'line',
        data: kdj.k,
        showSymbol: false,
        lineStyle: { width: 1, color: '#ff9800' },
        xAxisIndex: 3,
        yAxisIndex: 3,
      },
      {
        name: 'D',
        type: 'line',
        data: kdj.d,
        showSymbol: false,
        lineStyle: { width: 1, color: '#2196f3' },
        xAxisIndex: 3,
        yAxisIndex: 3,
      },
      {
        name: 'J',
        type: 'line',
        data: kdj.j,
        showSymbol: false,
        lineStyle: { width: 1, color: '#9c27b0' },
        xAxisIndex: 3,
        yAxisIndex: 3,
      },
      {
        name: '买入',
        type: 'scatter',
        data: buyPoints,
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: 'circle',
        symbolSize: 16,
        itemStyle: { color: COLOR_UP },
        label: { show: true, formatter: 'B', color: '#fff', fontSize: 10, fontWeight: 'bold' },
        tooltip: {
          formatter: (p: { data: { value: [string, number]; price: number } }) =>
            `买入信号<br/>${p.data.value[0]} ¥${p.data.price}`,
        },
      },
      {
        name: '卖出',
        type: 'scatter',
        data: sellPoints,
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: 'circle',
        symbolSize: 16,
        itemStyle: { color: COLOR_DOWN },
        label: { show: true, formatter: 'S', color: '#fff', fontSize: 10, fontWeight: 'bold' },
        tooltip: {
          formatter: (p: { data: { value: [string, number]; price: number } }) =>
            `卖出信号<br/>${p.data.value[0]} ¥${p.data.price}`,
        },
      },
    ] as echarts.SeriesOption[],
  }
}

function render(): void {
  if (!chart || props.bars.length === 0) return
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
    // 悬停十字光标移动 → 副图标题联动显示该位置的指标值
    chart.on('updateAxisPointer', (event) => {
      const idx = (event as { dataIndexInside?: number }).dataIndexInside
      if (idx === undefined || idx < 0 || !cached) return
      chart?.setOption({ title: buildTitles(idx) })
    })
  }
})

watch(() => [props.bars, props.markers], render, { deep: true })

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
