<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { BarPoint, SignalMarker } from '@/types'
import { computeKDJ, computeMACD, computeMA } from '@/utils/indicator'
const props = defineProps<{ bars: BarPoint[]; markers: SignalMarker[]; volumeUnit?: string }>()
const chartEl = ref<HTMLDivElement | null>(null)
const indicator = ref<'MACD' | 'KDJ' | 'NONE'>('MACD')
const fullscreen = ref(false),
  inspect = ref(false),
  showMa = ref(true),
  cursor = ref(-1)
const visibleBars = ref(0)
const UP = '#e53947',
  DOWN = '#159b75',
  maColors = ['#d3a02e', '#399bc4', '#9767c1', '#57a478']
const selectedIndex = computed(() => (cursor.value >= 0 ? cursor.value : props.bars.length - 1))
const selectedBar = computed(() => props.bars[selectedIndex.value])
const changes = computed(() => {
  const previous = props.bars[selectedIndex.value - 1]?.close
  return previous && selectedBar.value ? (selectedBar.value.close / previous - 1) * 100 : null
})
const maValues = computed(() =>
  [5, 10, 20, 60].map(
    (n) =>
      computeMA(
        props.bars.map((b) => b.close),
        n,
      )[selectedIndex.value],
  ),
)
let chart: echarts.ECharts | undefined, resize: ResizeObserver | undefined
let zoom = { start: 0, end: 100 }
let longPress: ReturnType<typeof setTimeout> | undefined
let origin: { x: number; y: number } | undefined
let touchInspect = false
function fmt(v?: number | null): string {
  return v == null ? '—' : v.toFixed(2)
}
function volume(v: number): string {
  return v >= 1e8
    ? `${(v / 1e8).toFixed(2)}亿`
    : v >= 1e4
      ? `${(v / 1e4).toFixed(2)}万`
      : v.toFixed(0)
}
function option(): echarts.EChartsOption {
  const bars = props.bars,
    dates = bars.map((b) => b.date),
    closes = bars.map((b) => b.close)
  const macd = computeMACD(closes),
    kdj = computeKDJ(
      bars.map((b) => b.high),
      bars.map((b) => b.low),
      closes,
    )
  const sub = indicator.value !== 'NONE'
  const grids = sub
    ? [
        { top: 40, height: '49%' },
        { top: '65%', height: '12%' },
        { top: '83%', height: '11%' },
      ]
    : [
        { top: 40, height: '64%' },
        { top: '81%', height: '13%' },
      ]
  const series: echarts.SeriesOption[] = [
    {
      name: 'K线',
      type: 'candlestick',
      data: bars.map((b) => [b.open, b.close, b.low, b.high]),
      barMaxWidth: 11,
      itemStyle: {
        color: '#fff',
        color0: DOWN,
        borderColor: UP,
        borderColor0: DOWN,
        borderWidth: 1.25,
      },
      markPoint: {
        symbol: 'circle',
        symbolSize: 16,
        data: props.markers
          .filter((m) => dates.includes(m.date))
          .map((m) => ({
            name: m.type === 'buy' ? '买入信号' : '卖出信号',
            coord: [
              m.date,
              m.type === 'buy'
                ? bars[dates.indexOf(m.date)]!.low
                : bars[dates.indexOf(m.date)]!.high,
            ],
            symbolOffset: m.type === 'buy' ? [0, 10] : [0, -10],
            value: m.type === 'buy' ? 'B' : 'S',
            itemStyle: { color: m.type === 'buy' ? UP : DOWN },
          })),
        label: { color: '#fff', fontSize: 9 },
      },
    },
  ]
  if (showMa.value)
    [5, 10, 20, 60].forEach((n, i) =>
      series.push({
        name: `MA${n}`,
        type: 'line',
        data: computeMA(closes, n),
        smooth: false,
        showSymbol: false,
        lineStyle: { width: 1, color: maColors[i] },
        silent: true,
      }),
    )
  series.push({
    name: '成交量',
    type: 'bar',
    xAxisIndex: 1,
    yAxisIndex: 1,
    barMaxWidth: 11,
    data: bars.map((b) => ({
      value: b.volume,
      itemStyle: { color: b.close >= b.open ? UP : DOWN, opacity: 0.8 },
    })),
  })
  if (indicator.value === 'MACD') {
    series.push({
      name: 'MACD',
      type: 'bar',
      xAxisIndex: 2,
      yAxisIndex: 2,
      data: macd.macd.map((v) => ({ value: v, itemStyle: { color: (v ?? 0) >= 0 ? UP : DOWN } })),
    })
    ;[macd.dif, macd.dea].forEach((values, i) =>
      series.push({
        name: ['DIF', 'DEA'][i],
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: values,
        showSymbol: false,
        lineStyle: { width: 1, color: maColors[i] },
      }),
    )
  } else if (indicator.value === 'KDJ') {
    ;[kdj.k, kdj.d, kdj.j].forEach((values, i) =>
      series.push({
        name: ['K', 'D', 'J'][i],
        type: 'line',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: values,
        showSymbol: false,
        lineStyle: { width: 1, color: maColors[i] },
      }),
    )
  }
  const i = selectedIndex.value
  const subText =
    indicator.value === 'MACD'
      ? `MACD(12,26,9)  DIF ${fmt(macd.dif[i])}  DEA ${fmt(macd.dea[i])}  MACD ${fmt(macd.macd[i])}`
      : `KDJ(9,3,3)  K ${fmt(kdj.k[i])}  D ${fmt(kdj.d[i])}  J ${fmt(kdj.j[i])}`
  return {
    animation: false,
    backgroundColor: '#fff',
    grid: grids.map((g) => ({ ...g, left: 8, right: 54 })),
    title: [
      {
        text: `成交量 ${selectedBar.value ? volume(selectedBar.value.volume) : '—'} ${props.volumeUnit === 'lot100' ? '手' : props.volumeUnit === 'share' ? '股' : '源单位'}`,
        top: sub ? '60%' : '76%',
        left: 6,
        textStyle: { fontSize: 10, fontWeight: 'normal', color: '#7b8798' },
      },
      ...(sub
        ? [
            {
              text: subText,
              top: '78%',
              left: 6,
              textStyle: { fontSize: 10, fontWeight: 'normal' as const, color: '#7b8798' },
            },
          ]
        : []),
    ],
    tooltip: {
      trigger: 'axis',
      showContent: false,
      triggerOn: 'mousemove|click|mousewheel',
      axisPointer: { type: 'cross' },
      renderMode: 'richText',
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }], lineStyle: { type: 'dashed', color: '#8994a5' } },
    xAxis: grids.map((_, idx) => ({
      type: 'category' as const,
      data: dates,
      gridIndex: idx,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#e7eaf0' } },
      axisTick: { show: false },
      axisLabel: {
        show: idx === grids.length - 1,
        color: '#8c96a5',
        fontSize: 10,
        hideOverlap: true,
        formatter: (v: string) => v.slice(5),
      },
      axisPointer: { show: true, label: { backgroundColor: '#637083' } },
    })),
    yAxis: grids.map((_, idx) => ({
      type: 'value' as const,
      gridIndex: idx,
      position: 'right' as const,
      scale: true,
      splitNumber: idx === 0 ? 4 : 2,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: '#8c96a5',
        fontSize: 10,
        formatter: idx === 1 ? volume : (v: number) => fmt(v),
      },
      splitLine: { lineStyle: { color: '#edf0f4', type: 'dashed' as const } },
    })),
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: grids.map((_, i) => i),
        ...zoom,
        minValueSpan: Math.min(8, Math.max(1, bars.length - 1)),
        zoomOnMouseWheel: true,
        moveOnMouseWheel: false,
        moveOnMouseMove: !inspect.value,
        disabled: inspect.value,
      },
    ],
    series,
  }
}
function render(): void {
  visibleBars.value = Math.min(
    props.bars.length,
    Math.round(((zoom.end - zoom.start) / 100) * Math.max(0, props.bars.length - 1)) + 1,
  )
  if (!chart) return
  if (!props.bars.length) {
    chart.clear()
    return
  }
  chart.setOption(option(), true)
}
function reset(): void {
  const n = window.innerWidth < 760 ? 40 : 70
  zoom = {
    start: Math.max(0, ((props.bars.length - n) / Math.max(1, props.bars.length - 1)) * 100),
    end: 100,
  }
  cursor.value = -1
  render()
}
function magnify(factor: number): void {
  const span = Math.max(
    (100 * Math.min(8, props.bars.length)) / Math.max(1, props.bars.length),
    Math.min(100, (zoom.end - zoom.start) * factor),
  )
  zoom = { start: Math.max(0, zoom.end - span), end: zoom.end }
  render()
}
function pointer(e: PointerEvent): void {
  const box = chartEl.value?.getBoundingClientRect()
  if (box)
    chart?.dispatchAction({
      type: 'updateAxisPointer',
      currTrigger: 'mousemove',
      x: e.clientX - box.left,
      y: e.clientY - box.top,
    })
}
function down(e: PointerEvent): void {
  if (e.pointerType !== 'touch' || !e.isPrimary) return
  origin = { x: e.clientX, y: e.clientY }
  clearTimeout(longPress)
  longPress = setTimeout(() => {
    touchInspect = true
    inspect.value = true
    chartEl.value?.setPointerCapture(e.pointerId)
    render()
    pointer(e)
  }, 380)
}
function move(e: PointerEvent): void {
  if (touchInspect) {
    if (e.cancelable) e.preventDefault()
    pointer(e)
  } else if (origin && Math.hypot(e.clientX - origin.x, e.clientY - origin.y) > 8)
    clearTimeout(longPress)
}
function up(): void {
  clearTimeout(longPress)
  origin = undefined
  if (touchInspect) {
    touchInspect = false
    inspect.value = false
    render()
  }
}
function keys(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    fullscreen.value = false
    inspect.value = false
  }
  if (e.target === chartEl.value && ['ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault()
    cursor.value = Math.max(
      0,
      Math.min(props.bars.length - 1, selectedIndex.value + (e.key === 'ArrowLeft' ? -1 : 1)),
    )
  }
}
watch(() => props.bars, reset)
watch(() => props.markers, render)
watch([indicator, showMa, inspect], render)
watch(fullscreen, () => requestAnimationFrame(() => chart?.resize()))
watch(cursor, () => {
  if (chart) chart.setOption({ title: option().title })
})
onMounted(() => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  resize = new ResizeObserver(() => chart?.resize())
  resize.observe(chartEl.value)
  chart.on('updateAxisPointer', (event) => {
    const info = (event as { axesInfo?: { value: number | string }[] }).axesInfo?.[0]
    if (!info) return
    const idx =
      typeof info.value === 'number'
        ? info.value
        : props.bars.findIndex((b) => b.date === info.value)
    if (idx >= 0 && idx < props.bars.length) cursor.value = idx
  })
  chart.on('datazoom', (event) => {
    const e = event as { start?: number; end?: number; batch?: { start: number; end: number }[] }
    const p = e.batch?.[0] ?? e
    if (p.start != null && p.end != null) {
      zoom = { start: p.start, end: p.end }
      visibleBars.value = Math.min(
        props.bars.length,
        Math.round(((zoom.end - zoom.start) / 100) * Math.max(0, props.bars.length - 1)) + 1,
      )
    }
  })
  document.addEventListener('keydown', keys)
  reset()
})
onBeforeUnmount(() => {
  clearTimeout(longPress)
  document.removeEventListener('keydown', keys)
  resize?.disconnect()
  chart?.dispose()
})
</script>
<template>
  <div class="kline-shell" :class="{ fullscreen }" data-testid="kline-terminal">
    <div class="kline-toolbar">
      <div class="indicator-tabs" role="group" aria-label="副图指标">
        <button
          v-for="item in ['MACD', 'KDJ', 'NONE'] as const"
          :key="item"
          :aria-pressed="indicator === item"
          :class="{ active: indicator === item }"
          @click="indicator = item"
        >
          {{ item === 'NONE' ? '仅成交量' : item }}
        </button>
      </div>
      <div class="chart-tools">
        <button :aria-pressed="showMa" @click="showMa = !showMa">MA</button
        ><button :aria-pressed="inspect" aria-label="十字线模式" @click="inspect = !inspect">
          十字线</button
        ><button aria-label="缩小K线" @click="magnify(1.4)">−</button
        ><button aria-label="放大K线" @click="magnify(0.7)">＋</button
        ><button aria-label="复位到最近行情" @click="reset">复位</button
        ><button
          :aria-label="fullscreen ? '退出图表全屏' : '展开图表'"
          @click="fullscreen = !fullscreen"
        >
          {{ fullscreen ? '退出' : '全屏' }}
        </button>
      </div>
    </div>
    <div class="candle-readout" aria-live="off">
      <span>{{ selectedBar?.date ?? '暂无行情' }}</span
      ><span
        >开 <b>{{ fmt(selectedBar?.open) }}</b></span
      ><span
        >高 <b>{{ fmt(selectedBar?.high) }}</b></span
      ><span
        >低 <b>{{ fmt(selectedBar?.low) }}</b></span
      ><span
        >收 <b>{{ fmt(selectedBar?.close) }}</b></span
      ><span :class="(changes ?? 0) >= 0 ? 'up' : 'down'">{{
        changes == null ? '—' : `${changes >= 0 ? '+' : ''}${changes.toFixed(2)}%`
      }}</span>
    </div>
    <div class="ma-readout">
      <span v-for="(n, i) in [5, 10, 20, 60]" :key="n" :style="{ color: maColors[i] }"
        >MA{{ n }}: {{ fmt(maValues[i]) }}</span
      >
    </div>
    <div
      ref="chartEl"
      role="img"
      tabindex="0"
      :aria-label="`K线图，最新收盘价 ${bars.at(-1)?.close ?? '暂无'}`"
      class="chart-canvas"
      :class="{ inspecting: inspect }"
      @pointerdown.capture="down"
      @pointermove.capture="move"
      @pointerup.capture="up"
      @pointercancel.capture="up"
      @contextmenu.prevent
    />
    <p class="gesture-hint">
      {{ inspect ? '十字线查看中' : '左右拖动查看历史 · 滚轮 / 双指缩放 · 长按查看十字线'
      }}<span data-testid="candle-count"
        >{{ visibleBars }} / {{ bars.length }} 根 · 收盘信号 B / S</span
      >
    </p>
  </div>
</template>
<style scoped>
.kline-shell {
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  background: #fff;
  color: #4b5563;
}
.kline-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px;
  padding: 7px 2px;
}
.indicator-tabs,
.chart-tools {
  display: flex;
  gap: 2px;
  align-items: center;
}
button {
  border: 0;
  background: transparent;
  border-radius: 4px;
  color: #8290a0;
  font-size: 11px;
  padding: 5px 7px;
  cursor: pointer;
}
button.active,
button[aria-pressed='true'] {
  color: #d63642;
  background: #fff1f2;
}
button:hover {
  background: #f5f7fa;
}
.candle-readout {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 12px;
  font-size: 11px;
  min-height: 24px;
  align-items: center;
  color: #8993a1;
}
.candle-readout b {
  color: #4b5563;
  font-weight: 500;
}
.candle-readout .up {
  color: #e53947;
}
.candle-readout .down {
  color: #159b75;
}
.ma-readout {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 10px;
  padding-top: 5px;
}
.chart-canvas {
  flex: 1;
  min-height: 320px;
  width: 100%;
  touch-action: pan-y;
}
.chart-canvas.inspecting {
  touch-action: none;
}
.gesture-hint {
  display: flex;
  justify-content: space-between;
  color: #a0a8b5;
  font-size: 10px;
  margin: 2px 4px 0;
}
.fullscreen {
  position: fixed;
  inset: 0;
  z-index: 3000;
  height: 100dvh;
  padding: 18px;
  box-sizing: border-box;
}
.fullscreen .chart-canvas {
  min-height: 0;
}
@media (max-width: 760px) {
  .kline-toolbar {
    align-items: flex-start;
  }
  .chart-tools {
    flex-wrap: wrap;
  }
  button {
    padding: 5px;
    font-size: 10px;
  }
  .candle-readout {
    gap: 4px 9px;
    font-size: 10px;
  }
  .gesture-hint span {
    display: none;
  }
  .ma-readout {
    gap: 3px 9px;
  }
}
</style>
