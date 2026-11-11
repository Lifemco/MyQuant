/* 复刻 ThsKLineChart 的完整 option,逐步加配置定位 grid 右缘发散的根因 */
import * as echarts from 'echarts'

// —— 指标函数的 JS 复刻(与 src/utils/indicator.ts 一致) ——
const round2 = (v) => Math.round(v * 100) / 100
function computeMA(values, w) {
  const r = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= w) sum -= values[i - w]
    r.push(i >= w - 1 ? round2(sum / w) : null)
  }
  return r
}
function computeEMA(values, w) {
  const k = 2 / (w + 1)
  const r = []
  let prev = values[0] ?? 0
  for (const v of values) {
    prev = v * k + prev * (1 - k)
    r.push(prev)
  }
  return r
}
function computeMACD(values) {
  const ema12 = computeEMA(values, 12)
  const ema26 = computeEMA(values, 26)
  const dif = ema12.map((v, i) => round2(v - ema26[i]))
  const dea = computeEMA(dif, 9).map(round2)
  const macd = dif.map((v, i) => round2(2 * (v - dea[i])))
  return { dif, dea, macd }
}
function computeKDJ(highs, lows, closes, n = 9) {
  const k = [], d = [], j = []
  let pk = 50, pd = 50
  for (let i = 0; i < closes.length; i++) {
    if (i < n - 1) { k.push(null); d.push(null); j.push(null); continue }
    let hh = -Infinity, ll = Infinity
    for (let m = i - n + 1; m <= i; m++) { if (highs[m] > hh) hh = highs[m]; if (lows[m] < ll) ll = lows[m] }
    const rsv = hh === ll ? 50 : ((closes[i] - ll) / (hh - ll)) * 100
    pk = (2 / 3) * pk + (1 / 3) * rsv
    pd = (2 / 3) * pd + (1 / 3) * pk
    k.push(round2(pk)); d.push(round2(pd)); j.push(round2(3 * pk - 2 * pd))
  }
  return { k, d, j }
}

// —— 合成 641 根日线数据 ——
const N = 641
const dates = [], bars = []
let price = 15
for (let i = 0; i < N; i++) {
  dates.push(`2024-01-${String((i % 28) + 1).padStart(2, '0')}-${i}`)
  price = price * (1 + (Math.sin(i / 30) * 0.02))
  bars.push({ date: dates[i], open: price * 0.99, high: price * 1.02, low: price * 0.98, close: price, volume: 10000 + i * 10 })
}

const closes = bars.map((b) => b.close)
const highs = bars.map((b) => b.high)
const lows = bars.map((b) => b.low)
const klineData = bars.map((b) => [b.open, b.close, b.low, b.high])
const volumeData = bars.map((b) => ({ value: b.volume, itemStyle: { color: b.close >= b.open ? '#ef5350' : '#26a69a' } }))
const macd = computeMACD(closes)
const macdBars = macd.macd.map((v) => ({ value: v, itemStyle: { color: (v ?? 0) >= 0 ? '#ef5350' : '#26a69a' } }))
const kdj = computeKDJ(highs, lows, closes)
const MA_COLORS = { ma5: '#ff9800', ma10: '#2196f3', ma20: '#9c27b0', ma60: '#607d8b' }
const maSeries = [5, 10, 20, 60].map((w) => ({
  name: `MA${w}`, type: 'line', color: MA_COLORS[`ma${w}`], data: computeMA(closes, w),
  smooth: true, showSymbol: false, lineStyle: { width: 1 }, xAxisIndex: 0, yAxisIndex: 0,
}))

const TITLE_STYLE = { fontSize: 12, color: '#303133', fontWeight: 'bold' }

function baseOption() {
  return {
    animation: false,
    legend: { data: ['MA5', 'MA10', 'MA20', 'MA60'], top: 2, textStyle: { fontSize: 11 } },
    title: [
      { text: '成交量 1.2万', left: 64, top: '30.5%', textStyle: TITLE_STYLE },
      { text: 'MACD(12,26,9) DIF 0.1', left: 64, top: '56%', textStyle: TITLE_STYLE },
      { text: 'KDJ(9,3,3) K 55', left: 64, top: '81.5%', textStyle: TITLE_STYLE },
    ],
    grid: [
      { left: 56, right: 16, top: 30, height: '17.5%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '30%', height: '20%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '55.5%', height: '20%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
      { left: 56, right: 16, top: '81%', height: '19%', show: true, borderColor: '#dcdfe6', borderWidth: 1 },
    ],
    xAxis: [0, 1, 2, 3].map((i) => ({
      type: 'category', data: dates, gridIndex: i, boundaryGap: true,
      axisLabel: { show: i === 0, fontSize: 10, hideOverlap: true, margin: 4, showMaxLabel: true },
      axisTick: { show: false }, axisLine: { show: i === 0 },
    })),
    yAxis: [
      { scale: true, gridIndex: 0, splitNumber: 4, axisLabel: { fontSize: 10 } },
      { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { fontSize: 10, formatter: (v) => (v >= 1e8 ? `${(v / 1e8).toFixed(1)}亿` : `${(v / 1e4).toFixed(0)}万`) } },
      { scale: true, gridIndex: 2, splitNumber: 2, axisLabel: { fontSize: 10 } },
      { scale: true, gridIndex: 3, splitNumber: 2, axisLabel: { fontSize: 10 } },
    ],
    series: [
      { name: 'K线', type: 'candlestick', data: klineData, xAxisIndex: 0, yAxisIndex: 0 },
      ...maSeries,
      { name: '成交量', type: 'bar', data: volumeData, xAxisIndex: 1, yAxisIndex: 1 },
      { name: 'MACD', type: 'bar', data: macdBars, xAxisIndex: 2, yAxisIndex: 2 },
      { name: 'DIF', type: 'line', data: macd.dif, showSymbol: false, xAxisIndex: 2, yAxisIndex: 2 },
      { name: 'DEA', type: 'line', data: macd.dea, showSymbol: false, xAxisIndex: 2, yAxisIndex: 2 },
      { name: 'K', type: 'line', data: kdj.k, showSymbol: false, xAxisIndex: 3, yAxisIndex: 3 },
      { name: 'D', type: 'line', data: kdj.d, showSymbol: false, xAxisIndex: 3, yAxisIndex: 3 },
      { name: 'J', type: 'line', data: kdj.j, showSymbol: false, xAxisIndex: 3, yAxisIndex: 3 },
    ],
  }
}

function rects(option, label) {
  const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: 1350, height: 600 })
  chart.setOption(option)
  const out = [0, 1, 2, 3].map((i) => {
    const rect = chart.getModel().getComponent('grid', i).coordinateSystem.getRect()
    return `g${i}: x=${rect.x.toFixed(0)} w=${rect.width.toFixed(1)} right=${(rect.x + rect.width).toFixed(1)}`
  })
  chart.dispose()
  console.log(label, '=>', out.join(' | '))
}

// 实验 A:完整配置(不含 dataZoom)
rects(baseOption(), 'A 无dataZoom')

// 实验 B:加上 inside dataZoom
const optB = baseOption()
optB.dataZoom = [{ type: 'inside', xAxisIndex: [0, 1, 2, 3], start: 0, end: 100, zoomOnMouseWheel: true, moveOnMouseWheel: true }]
rects(optB, 'B 有dataZoom')

// 实验 C:加 tooltip + axisPointer link
const optC = baseOption()
optC.tooltip = { trigger: 'axis', confine: true, axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] } }
optC.axisPointer = { link: [{ xAxisIndex: 'all' }] }
rects(optC, 'C 有axisPointerLink')

// 实验 D:axisLabel 不带 showMaxLabel/hideOverlap
const optD = baseOption()
optD.xAxis = [0, 1, 2, 3].map((i) => ({
  type: 'category', data: dates, gridIndex: i, boundaryGap: true,
  axisLabel: { show: i === 0, fontSize: 10 }, axisTick: { show: false }, axisLine: { show: i === 0 },
}))
rects(optD, 'D 简化axisLabel')

// 实验 E:showMaxLabel + alignMaxLabel 右对齐(期望对齐)
const optE = baseOption()
optE.xAxis = [0, 1, 2, 3].map((i) => ({
  type: 'category', data: dates, gridIndex: i, boundaryGap: true,
  axisLabel: {
    show: i === 0, fontSize: 10, hideOverlap: true, margin: 4,
    showMinLabel: true, showMaxLabel: true,
    alignMinLabel: 'left', alignMaxLabel: 'right',
  },
  axisTick: { show: false }, axisLine: { show: i === 0 },
}))
rects(optE, 'E 首尾标签对齐')
