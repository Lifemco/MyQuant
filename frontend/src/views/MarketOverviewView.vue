<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { collectMarket, getMarketOverview } from '@/api/market'
import type { MarketOverview, SectionKey } from '@/api/market'
import { extractErrorMessage } from '@/api/client'
import MarketChart from '@/components/MarketChart.vue'

const result = ref<MarketOverview | null>(null)
const loading = ref(false)
const error = ref('')
const indexCode = ref('000001')
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const cards: { key: SectionKey; number: string; title: string; subtitle: string }[] = [
  { key: 'trend', number: '01', title: '大盘走势与成交额', subtitle: '指数点位 · 成交活跃度' },
  { key: 'industry', number: '02', title: '行业涨跌热力图', subtitle: '行业轮动 · 市值分布' },
  {
    key: 'distribution',
    number: '03',
    title: '全市场涨跌分布',
    subtitle: '沪深京 A 股 · 有效交易样本',
  },
  {
    key: 'breadth',
    number: '04',
    title: '站上 MA20 / MA60 占比',
    subtitle: '沪深 A 股 · 市场宽度',
  },
  {
    key: 'style',
    number: '05',
    title: '规模与价值成长风格',
    subtitle: '共同基日 = 100 · 价格指数',
  },
  {
    key: 'valuation',
    number: '06',
    title: '市场估值历史分位',
    subtitle: '沪深300 PE-TTM · 近五年滚动分位',
  },
]
const statuses = {
  ok: '已更新',
  partial: '口径受限 / 部分数据',
  stale: '缓存数据 / 待更新',
  unavailable: '暂无数据',
}
const trend = computed(() => {
  const data = result.value?.sections.trend.data
  return data?.find((series) => series.code === indexCode.value) ?? data?.[0]
})
const distribution = computed(() => result.value?.sections.distribution.data)
const breadth = computed(() => result.value?.sections.breadth.data)
const lastBreadth = computed(() => breadth.value?.points.at(-1))
const lastValuation = computed(() => result.value?.sections.valuation.data?.points.at(-1))
function number(value: number | null | undefined, digits = 1): string {
  return value == null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}
function timestamp(value: string | null): string {
  return value
    ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
    : '—'
}

const options = computed<Record<SectionKey, EChartsOption>>(() => {
  const sections = result.value?.sections
  const line = { type: 'line' as const, showSymbol: true, symbolSize: 3, connectNulls: false }
  const base: EChartsOption = {
    animation: false,
    color: ['#2563eb', '#d97706', '#7c3aed', '#dc2626', '#059669'],
    tooltip: { trigger: 'axis', renderMode: 'richText' },
    grid: { left: 58, right: 52, top: 38, bottom: 72 },
    legend: { bottom: 0, type: 'scroll' },
    xAxis: { type: 'category', boundaryGap: false },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#edf1f5' } } },
  }
  const industry = sections?.industry.data ?? []
  const style = sections?.style.data
  const val = sections?.valuation.data?.points ?? []
  const width = breadth.value?.points ?? []
  return {
    trend: {
      ...base,
      xAxis: { type: 'category', data: trend.value?.points.map((p) => p.date) },
      yAxis: [
        { type: 'value', name: '点', scale: true },
        { type: 'value', name: '亿元', splitLine: { show: false } },
      ],
      series: [
        {
          type: 'bar',
          name: '成交额（亿元）',
          yAxisIndex: 1,
          data: trend.value?.points.map((p) => p.amount / 1e8),
          itemStyle: { color: '#dbeafe' },
        },
        {
          ...line,
          name: trend.value?.name ?? '指数',
          data: trend.value?.points.map((p) => p.close),
        },
      ],
      dataZoom: [{ type: 'inside' }],
    },
    industry: {
      animation: false,
      tooltip: { trigger: 'item', renderMode: 'richText', formatter: '{b}' },
      series: [
        {
          type: 'treemap',
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          left: 0,
          right: 0,
          top: 12,
          bottom: 12,
          visibleMin: 0,
          data: industry.map((row) => ({
            name: `${row.name}\n${number(row.change, 2)}%`,
            value: row.size,
            itemStyle: {
              color: row.change > 0 ? '#dc5b62' : row.change < 0 ? '#299b83' : '#94a3b8',
            },
          })),
          label: { fontSize: 11, overflow: 'truncate' },
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
        },
      ],
    },
    distribution: {
      ...base,
      legend: { show: false },
      grid: { left: 45, right: 16, top: 30, bottom: 60 },
      xAxis: {
        type: 'category',
        data: distribution.value?.bins.map((p) => p.label),
        axisLabel: { rotate: 35, fontSize: 10 },
      },
      yAxis: { type: 'value', name: '家', minInterval: 1 },
      series: [
        {
          type: 'bar',
          name: '股票数',
          data: distribution.value?.bins.map((p, i) => ({
            value: p.count,
            itemStyle: { color: i < 5 ? '#299b83' : i > 5 ? '#dc5b62' : '#94a3b8' },
          })),
        },
      ],
    },
    breadth: {
      ...base,
      xAxis: { type: 'category', data: width.map((p) => p.date) },
      tooltip: {
        trigger: 'axis',
        renderMode: 'richText',
        formatter: (params) => {
          const first = Array.isArray(params) ? params[0] : params
          const point = first ? width[first.dataIndex] : undefined
          return point
            ? `${point.date}\nMA20: ${number(point.ma20)}% · 有效 ${point.eligible20} 只\nMA60: ${number(point.ma60)}% · 有效 ${point.eligible60} 只`
            : ''
        },
      },
      yAxis: { type: 'value', name: '%', min: 0, max: 100 },
      series: [
        { ...line, name: '站上 MA20（%）', data: width.map((p) => p.ma20) },
        { ...line, name: '站上 MA60（%）', data: width.map((p) => p.ma60) },
      ],
    },
    style: {
      ...base,
      xAxis: { type: 'category', data: style?.dates },
      yAxis: { type: 'value', scale: true, name: '基日=100' },
      series: style?.series.map((s) => ({ ...line, name: s.name, data: s.values })),
    },
    valuation: {
      ...base,
      xAxis: { type: 'category', data: val.map((p) => p.date) },
      yAxis: [
        { type: 'value', name: 'PE（倍）', scale: true },
        { type: 'value', name: '分位（%）', min: 0, max: 100, splitLine: { show: false } },
      ],
      series: [
        { ...line, name: 'PE-TTM（倍）', data: val.map((p) => p.pe) },
        { ...line, name: '历史分位（%）', yAxisIndex: 1, data: val.map((p) => p.percentile) },
      ],
    },
  }
})

function schedule(): void {
  clearTimeout(timer)
  if (!disposed && result.value?.job.running) timer = setTimeout(() => void load(), 2500)
}
async function load(): Promise<void> {
  if (disposed || loading.value) return
  loading.value = true
  try {
    result.value = await getMarketOverview()
    error.value = ''
  } catch (err) {
    error.value = extractErrorMessage(err)
  } finally {
    loading.value = false
    schedule()
  }
}
async function collect(kind: 'refresh' | 'breadth'): Promise<void> {
  if (loading.value || result.value?.job.running) return
  clearTimeout(timer)
  loading.value = true
  try {
    result.value = await collectMarket(kind)
    error.value = ''
  } catch (err) {
    error.value = extractErrorMessage(err)
  } finally {
    loading.value = false
    schedule()
  }
}
onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <main class="overview-page">
    <header class="overview-header">
      <div>
        <p class="eyebrow">MARKET OVERVIEW / A-SHARES</p>
        <h1>市场总览</h1>
        <p class="intro">从指数、行业、宽度与估值，观察市场的整体状态。</p>
      </div>
      <div class="actions">
        <button :disabled="loading || result?.job.running" @click="load">重读缓存</button>
        <button
          class="primary"
          :disabled="loading || result?.job.running"
          @click="collect('refresh')"
        >
          刷新市场数据
        </button>
      </div>
    </header>
    <div v-if="error" role="alert" class="notice error">
      {{ error }}<button :disabled="loading" @click="load">重试</button>
    </div>
    <div v-if="result?.job.running" role="status" class="notice">
      {{ result.job.kind === 'breadth' ? '正在采集全市场历史数据' : '正在刷新市场数据' }}
      · {{ result.job.done ?? 0 }} / {{ result.job.total || '准备中' }}
      <span v-if="result.job.failed"> · 失败 {{ result.job.failed }} 只</span>
      <span> · 可离开页面，后台继续采集。</span>
    </div>
    <div v-if="result?.job.error" role="alert" class="notice error">{{ result.job.error }}</div>
    <div class="scope-note">
      A股视角 · 时间统一为北京时间 · 指数使用已收盘日线 · 各图独立标注日期与覆盖范围
    </div>
    <div v-if="!result && loading" role="status" class="notice">正在读取市场总览…</div>
    <div class="chart-grid">
      <section
        v-for="card in cards"
        :key="card.key"
        :aria-label="card.title"
        class="chart-card"
        :data-testid="`market-${card.key}`"
      >
        <div class="card-heading">
          <div>
            <p class="card-subtitle">{{ card.number }} / {{ card.subtitle }}</p>
            <h2>{{ card.title }}</h2>
          </div>
          <span class="badge" :class="result?.sections[card.key].status ?? 'unavailable'">{{
            statuses[result?.sections[card.key].status ?? 'unavailable']
          }}</span>
        </div>
        <div class="chart-summary">
          <select
            v-if="card.key === 'trend' && result?.sections.trend.data?.length"
            v-model="indexCode"
            aria-label="大盘指数"
          >
            <option
              v-for="series in result.sections.trend.data"
              :key="series.code"
              :value="series.code"
            >
              {{ series.name }}
            </option>
          </select>
          <span v-if="card.key === 'trend' && trend"
            >最近收盘 {{ number(trend.points.at(-1)?.close, 2) }} 点 ·
            {{ trend.points.at(-1)?.date }}</span
          >
          <span v-if="card.key === 'industry'">红色上涨 · 绿色下跌 · 面积代表市值</span>
          <span v-if="card.key === 'distribution' && distribution"
            >有效 {{ distribution.valid }} / {{ distribution.total }} · 上涨 {{ distribution.up }} ·
            平盘 {{ distribution.flat }} · 下跌 {{ distribution.down }} · 排除
            {{ distribution.excluded }}</span
          >
          <span v-if="card.key === 'breadth' && breadth"
            >已采集 {{ breadth.collected }} / {{ breadth.total }} · 最新 MA20
            {{ number(lastBreadth?.ma20) }}%（{{ lastBreadth?.eligible20 }} 只） · MA60
            {{ number(lastBreadth?.ma60) }}%（{{ lastBreadth?.eligible60 }} 只）</span
          >
          <span v-if="card.key === 'style' && result?.sections.style.data"
            >比较基日 {{ result.sections.style.data.baseDate }}</span
          >
          <span v-if="card.key === 'valuation' && lastValuation"
            >PE {{ number(lastValuation.pe, 2) }} 倍 · 分位 {{ number(lastValuation.percentile) }}%
            · 窗口 {{ lastValuation.samples }} 个样本</span
          >
        </div>
        <MarketChart
          v-if="result?.sections[card.key].data"
          :option="options[card.key]"
          :label="card.title"
        />
        <div v-else class="empty-state">
          <span class="empty-icon">—</span>
          <p>{{ loading ? '正在读取数据' : '尚无可展示的数据' }}</p>
          <small>{{
            card.key === 'breadth'
              ? '先刷新市场证券名单，再构建全市场宽度。'
              : '刷新后展示真实市场数据；采集失败会保留已有缓存。'
          }}</small>
        </div>
        <div v-if="card.key === 'breadth'" class="breadth-action">
          <button :disabled="loading || result?.job.running" @click="collect('breadth')">
            构建 / 更新全市场宽度</button
          ><small>首次需下载全市场历史，耗时较长；支持当日缓存续采。</small>
        </div>
        <footer class="card-footer">
          <p v-if="result?.sections[card.key].error" class="section-error">
            {{ result.sections[card.key].error }}
          </p>
          <p>{{ result?.sections[card.key].notes || '等待采集数据。' }}</p>
          <p class="provenance">
            {{ result?.sections[card.key].source ?? '尚未采集' }} · 行情日期
            {{ result?.sections[card.key].asOf ?? '源未确认' }} · 抓取
            {{ timestamp(result?.sections[card.key].fetchedAt ?? null) }}
          </p>
        </footer>
      </section>
    </div>
  </main>
</template>

<style scoped>
.overview-page {
  width: 100%;
  box-sizing: border-box;
  max-width: 1540px;
  margin: 0 auto;
  padding: 28px 24px 48px;
  color: #1e293b;
  background: #f5f7fa;
}
.overview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.15em;
  color: #64748b;
  margin: 0 0 8px;
}
h1 {
  font-size: 28px;
  font-weight: 650;
  margin: 0;
}
.intro {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
}
.actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
button,
select {
  border: 1px solid #dbe2eb;
  border-radius: 6px;
  background: white;
  padding: 8px 12px;
  font-size: 12px;
  cursor: pointer;
  color: #334155;
}
button:hover {
  border-color: #2563eb;
  color: #2563eb;
}
button:disabled {
  opacity: 0.5;
  cursor: wait;
}
button.primary {
  background: #2563eb;
  color: white;
  border-color: #2563eb;
}
.scope-note {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 16px;
}
.notice {
  padding: 12px 16px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  margin-bottom: 14px;
  font-size: 13px;
}
.notice button {
  margin-left: 12px;
}
.error {
  background: #fff7ed;
  border-color: #fed7aa;
  color: #9a3412;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.chart-card {
  min-width: 0;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 20px;
  display: flex;
  flex-direction: column;
}
.card-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}
.card-subtitle {
  font-size: 11px;
  color: #64748b;
  margin: 0 0 7px;
}
h2 {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
}
.badge {
  white-space: nowrap;
  padding: 4px 7px;
  font-size: 10px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #64748b;
}
.badge.ok {
  background: #ecfdf5;
  color: #047857;
}
.badge.partial,
.badge.stale {
  background: #fffbeb;
  color: #a16207;
}
.chart-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 43px;
  font-size: 11px;
  color: #475569;
  margin-top: 8px;
}
.chart-summary select {
  padding: 4px 8px;
}
.empty-state {
  height: 310px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #64748b;
  text-align: center;
}
.empty-icon {
  font-size: 32px;
  color: #cbd5e1;
}
.empty-state p {
  margin: 12px 0 6px;
  font-size: 14px;
}
.empty-state small {
  font-size: 11px;
}
.breadth-action {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.breadth-action small {
  font-size: 10px;
  color: #64748b;
}
.card-footer {
  margin-top: auto;
  border-top: 1px solid #edf1f5;
  padding-top: 10px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.7;
}
.card-footer p {
  margin: 3px 0;
}
.provenance {
  color: #94a3b8;
  font-size: 10px;
}
.section-error {
  color: #b45309;
}
@media (max-width: 880px) {
  .chart-grid {
    grid-template-columns: 1fr;
  }
  .overview-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
@media (max-width: 480px) {
  .overview-page {
    padding: 20px 12px;
  }
  .chart-card {
    padding: 14px;
  }
  .card-heading {
    flex-wrap: wrap;
  }
}
</style>
