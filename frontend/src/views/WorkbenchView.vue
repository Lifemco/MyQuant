<script setup lang="ts">
import { ArrowLeftBold, ArrowRightBold, Refresh, Setting } from '@element-plus/icons-vue'
import { ElButton, ElCard, ElEmpty, ElIcon, ElMessage, ElSwitch } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { extractErrorMessage } from '@/api/client'
import { getChartData, getMinuteData } from '@/api/monitor'
import MinuteChart from '@/components/MinuteChart.vue'
import QuoteHeader from '@/components/QuoteHeader.vue'
import SignalPanel from '@/components/SignalPanel.vue'
import StrategyDrawer from '@/components/StrategyDrawer.vue'
import ThsKLineChart from '@/components/ThsKLineChart.vue'
import WatchlistPanel from '@/components/WatchlistPanel.vue'
import { useWatchlistStore } from '@/stores/watchlist'
import type { ChartData, MinuteData, Period } from '@/types'

const QUOTE_POLL_MS = 3000
type ChartTab = Period | 'minute'
const PERIOD_TABS: { value: ChartTab; label: string }[] = [
  { value: 'minute', label: '分时' },
  { value: 'day', label: '日线' },
  { value: 'week', label: '周线' },
  { value: 'month', label: '月线' },
]
const store = useWatchlistStore()
const hash = window.location.hash.replace('#', '')
const chartTab = ref<ChartTab>(
  PERIOD_TABS.some((t) => t.value === hash) ? (hash as ChartTab) : 'day',
)
const chartData = ref<ChartData | null>(null)
const minuteData = ref<MinuteData | null>(null)
const chartLoading = ref(false)
const drawerVisible = ref(false)
const autoRefresh = ref(true)
const previewOverride = ref<{ strategy: string; params: Record<string, number> } | null>(null)
const selected = computed(() => store.selected)
const listCollapsed = ref(false)
const SIGNAL_PANEL_HEIGHT = 260
const signalData = ref<ChartData | null>(null)
const signalAsOf = computed(() => signalData.value?.signalAsOf ?? selected.value?.signalAsOf ?? '')
let requestVersion = 0
let disposed = false

/** 图表与日线面板共享同一份请求上下文，过期响应不得写回。 */
async function reloadActive(): Promise<void> {
  const version = ++requestVersion
  const item = selected.value
  chartData.value = null
  minuteData.value = null
  signalData.value = null
  if (!item) {
    chartLoading.value = false
    return
  }
  const tab = chartTab.value
  const payload = {
    market: item.market,
    symbol: item.symbol,
    strategy: previewOverride.value?.strategy ?? item.strategy,
    params: { ...(previewOverride.value?.params ?? item.params) },
  }
  chartLoading.value = true
  const daily = getChartData({ ...payload, period: 'day' })
  const visual =
    tab === 'day'
      ? daily
      : tab === 'minute'
        ? getMinuteData(item.market, item.symbol)
        : getChartData({ ...payload, period: tab })
  const [chartResult, signalResult] = await Promise.allSettled([visual, daily])
  if (disposed || version !== requestVersion) return
  if (chartResult.status === 'fulfilled') {
    if (tab === 'minute') minuteData.value = chartResult.value as MinuteData
    else chartData.value = chartResult.value as ChartData
  } else ElMessage.error(extractErrorMessage(chartResult.reason))
  if (signalResult.status === 'fulfilled') signalData.value = signalResult.value
  else if (tab !== 'day') ElMessage.error(extractErrorMessage(signalResult.reason))
  chartLoading.value = false
}

async function loadMinute(): Promise<void> {
  const item = selected.value
  const version = requestVersion
  if (!item || chartTab.value !== 'minute') return
  try {
    const data = await getMinuteData(item.market, item.symbol)
    if (
      !disposed &&
      version === requestVersion &&
      store.selectedKey === `${item.market}/${item.symbol}`
    )
      minuteData.value = data
  } catch {
    /* 暂时失败保留同一标的的分时数据，其交易日期仍可见。 */
  }
}

async function handleRefresh(): Promise<void> {
  try {
    await store.refresh()
    await reloadActive()
    const failures = store.items.filter((item) => item.refreshError || item.error)
    if (failures.length)
      ElMessage.warning(
        failures.map((item) => `${item.name}: ${item.refreshError || item.error}`).join('；'),
      )
    else ElMessage.success('行情和信号已刷新')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
}

function handlePreview(strategy: string, params: Record<string, number>): void {
  previewOverride.value = { strategy, params: { ...params } }
  void reloadActive()
}

async function handleSaved(): Promise<void> {
  previewOverride.value = null
  await store.load()
  await reloadActive()
}

function handleTabChange(tab: ChartTab): void {
  chartTab.value = tab
  window.location.hash = tab
  void reloadActive()
}

watch(
  () => store.selectedKey,
  () => {
    previewOverride.value = null
    drawerVisible.value = false
    void reloadActive()
  },
)
watch(drawerVisible, (visible) => {
  if (!visible && previewOverride.value) {
    previewOverride.value = null
    void reloadActive()
  }
})

let pollTimer: ReturnType<typeof setInterval> | null = null
let polling = false
async function poll(): Promise<void> {
  if (polling || disposed || !autoRefresh.value) return
  polling = true
  try {
    if (!store.items.length) await store.load()
    await store.pollQuotes()
    await loadMinute()
  } catch {
    /* 初始化失败后继续重试。 */
  } finally {
    polling = false
  }
}
onMounted(async () => {
  try {
    await store.load()
    if (!disposed) {
      await store.pollQuotes()
      await reloadActive()
    }
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
  if (!disposed)
    pollTimer = setInterval(() => {
      void poll()
    }, QUOTE_POLL_MS)
})
onBeforeUnmount(() => {
  disposed = true
  requestVersion++
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <!-- 顶栏 -->
    <header
      class="flex h-12 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4"
    >
      <div class="flex items-center gap-2">
        <span class="text-base font-bold text-gray-800">量化工作台</span>
        <span class="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">监控模式</span>
      </div>
      <div class="flex items-center gap-3 text-sm text-gray-500">
        <span v-if="signalAsOf">已确认日线截至 {{ signalAsOf }}</span>
        <span v-if="previewOverride" class="text-amber-600">策略预览（未保存）</span>
        <span class="flex items-center gap-1">
          实时刷新(3s)
          <ElSwitch v-model="autoRefresh" size="small" />
        </span>
        <ElButton size="small" type="primary" :loading="store.refreshing" @click="handleRefresh">
          <ElIcon class="mr-1"><Refresh /></ElIcon>刷新K线/信号
        </ElButton>
      </div>
    </header>

    <div class="flex flex-1 items-stretch">
      <!-- 左侧:自选列表(可折叠,内部固定宽度防止压缩变形) -->
      <aside
        class="shrink-0 overflow-hidden bg-white transition-[width] duration-200"
        :class="listCollapsed ? 'w-0' : 'w-64 border-r border-gray-200'"
      >
        <div class="w-64">
          <WatchlistPanel />
        </div>
      </aside>
      <!-- 折叠把手:常驻细长条,点击收起/展开 -->
      <div
        class="flex w-3.5 shrink-0 cursor-pointer items-center justify-center bg-gray-100 text-gray-400 transition-colors hover:bg-blue-100 hover:text-blue-500"
        :title="listCollapsed ? '展开自选列表' : '收起自选列表'"
        @click="listCollapsed = !listCollapsed"
      >
        <ElIcon :size="10">
          <ArrowRightBold v-if="listCollapsed" />
          <ArrowLeftBold v-else />
        </ElIcon>
      </div>

      <!-- 右侧:行情 + 图表 + 信号,页面允许 Y 轴滚动 -->
      <main class="flex min-w-0 flex-1 flex-col gap-2 bg-gray-50 p-2">
        <ElEmpty v-if="!selected" description="从左侧添加并选择一只股票" class="mx-auto py-24" />

        <template v-else>
          <!-- 同花顺式行情面板 -->
          <div class="flex shrink-0 items-stretch gap-2">
            <div class="min-w-0 flex-1">
              <QuoteHeader :item="selected" :quote="store.selectedQuote" />
            </div>
            <div class="flex items-center rounded-lg border border-gray-200 bg-white px-3">
              <ElButton size="small" @click="drawerVisible = true">
                <ElIcon class="mr-1"><Setting /></ElIcon>策略设置 / 回测
              </ElButton>
            </div>
          </div>

          <!-- 图表卡:固定充裕高度,页面可滚动 -->
          <ElCard v-loading="chartLoading" shadow="never" :body-style="{ padding: '6px 8px' }">
            <!-- 周期选项卡(同花顺式) -->
            <div class="mb-1 flex items-center gap-1 border-b border-gray-100 px-1 pb-1">
              <button
                v-for="tab in PERIOD_TABS"
                :key="tab.value"
                class="rounded px-3 py-1 text-sm transition-colors"
                :class="
                  chartTab === tab.value
                    ? 'bg-blue-500 font-medium text-white'
                    : 'text-gray-500 hover:bg-gray-100'
                "
                @click="handleTabChange(tab.value)"
              >
                {{ tab.label }}
              </button>
              <span class="ml-auto text-xs text-gray-400">
                {{
                  chartTab === 'minute'
                    ? `分时交易日 ${minuteData?.date || '未知'}，3s 自动更新`
                    : '买卖点为该周期下的策略信号'
                }}
              </span>
            </div>

            <!-- 图表区域:固定高度,适应视口 -->
            <div class="h-[calc(100vh-330px)] min-h-[580px]">
              <MinuteChart v-if="chartTab === 'minute' && minuteData" :data="minuteData" />
              <ThsKLineChart
                v-else-if="chartTab !== 'minute' && chartData"
                :bars="chartData.bars"
                :markers="chartData.markers"
              />
            </div>
          </ElCard>

          <!-- 底部:买卖信号面板,与图表周期无关(固定日线口径),固定加大高度 -->
          <ElCard
            v-if="signalData"
            shadow="never"
            class="shrink-0"
            :style="{ height: SIGNAL_PANEL_HEIGHT + 'px' }"
            :body-style="{ padding: '8px 12px', height: '100%', 'box-sizing': 'border-box' }"
          >
            <SignalPanel
              :markers="signalData.markers"
              :holding="signalData.holding"
              :last-signal="signalData.lastSignal"
              :height="SIGNAL_PANEL_HEIGHT"
            />
          </ElCard>
        </template>
      </main>
    </div>

    <StrategyDrawer
      v-model="drawerVisible"
      :item="selected"
      @saved="handleSaved"
      @preview="handlePreview"
    />
  </div>
</template>
