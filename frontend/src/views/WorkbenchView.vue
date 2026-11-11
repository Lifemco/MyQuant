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

/** 快照轮询间隔(3s) */
const QUOTE_POLL_MS = 3000

type ChartTab = Period | 'minute'

const PERIOD_TABS: { value: ChartTab; label: string }[] = [
  { value: 'minute', label: '分时' },
  { value: 'day', label: '日线' },
  { value: 'week', label: '周线' },
  { value: 'month', label: '月线' },
]

const store = useWatchlistStore()

// 支持 URL hash 直达指定图表(#minute/#day/#week/#month),便于分享与调试
const initialTab = ((): ChartTab => {
  const hash = window.location.hash.replace('#', '')
  return PERIOD_TABS.some((t) => t.value === hash) ? (hash as ChartTab) : 'day'
})()
const chartTab = ref<ChartTab>(initialTab)
const chartData = ref<ChartData | null>(null)
const minuteData = ref<MinuteData | null>(null)
const chartLoading = ref(false)
const drawerVisible = ref(false)
const autoRefresh = ref(true)
const lastRefreshAt = ref<string>('')

// 抽屉编辑中的临时策略参数(未保存也可预览信号)
const previewOverride = ref<{ strategy: string; params: Record<string, number> } | null>(null)

const selected = computed(() => store.selected)

/** 左侧自选列表折叠状态 */
const listCollapsed = ref(false)

/** 信号面板固定高度(px) */
const SIGNAL_PANEL_HEIGHT = 260

/** 信号面板数据:固定日线口径,与图表周期无关 */
const signalData = ref<ChartData | null>(null)

/** 加载 K线(当前周期) */
async function loadChart(): Promise<void> {
  const item = selected.value
  if (!item || chartTab.value === 'minute') return
  chartLoading.value = true
  try {
    chartData.value = await getChartData({
      market: item.market,
      symbol: item.symbol,
      strategy: previewOverride.value?.strategy ?? item.strategy,
      params: previewOverride.value?.params ?? item.params,
      period: chartTab.value,
    })
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    chartLoading.value = false
  }
}

/** 加载信号面板数据:始终按日线计算;日线 tab 时直接复用图表数据 */
async function loadSignals(): Promise<void> {
  const item = selected.value
  if (!item) {
    signalData.value = null
    return
  }
  if (chartTab.value === 'day' && chartData.value) {
    signalData.value = chartData.value
    return
  }
  try {
    signalData.value = await getChartData({
      market: item.market,
      symbol: item.symbol,
      strategy: previewOverride.value?.strategy ?? item.strategy,
      params: previewOverride.value?.params ?? item.params,
      period: 'day',
    })
  } catch {
    // 信号加载失败保留旧数据
  }
}

/** 加载当日分时 */
async function loadMinute(silent = false): Promise<void> {
  const item = selected.value
  if (!item) return
  if (!silent) chartLoading.value = true
  try {
    minuteData.value = await getMinuteData(item.market, item.symbol)
  } catch {
    if (!silent) {
      minuteData.value = null
      ElMessage.warning('分时数据暂不可用(可能非交易日或市场不支持)')
    }
  } finally {
    if (!silent) chartLoading.value = false
  }
}

/** 手动刷新:抓最新K线、重算信号、重载图表 */
async function handleRefresh(): Promise<void> {
  try {
    await store.refresh()
    await reloadActive()
    lastRefreshAt.value = new Date().toLocaleTimeString('zh-CN')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
}

async function reloadActive(): Promise<void> {
  if (chartTab.value === 'minute') {
    await loadMinute()
  } else {
    await loadChart()
  }
  await loadSignals()
}

/** 抽屉参数变化 → 图表用临时参数重算信号(不保存) */
function handlePreview(strategy: string, params: Record<string, number>): void {
  previewOverride.value = { strategy, params }
  loadChart()
  loadSignals()
}

/** 抽屉保存成功 → 清除临时参数,刷新列表、图表与信号 */
async function handleSaved(): Promise<void> {
  previewOverride.value = null
  await store.load()
  await reloadActive()
}

function handleTabChange(tab: ChartTab): void {
  chartTab.value = tab
  window.location.hash = tab
  reloadActive()
}

// 切换选中股票时清除预览覆盖并重载
watch(
  () => store.selectedKey,
  () => {
    previewOverride.value = null
    reloadActive()
  },
)

let pollTimer: ReturnType<typeof setInterval> | null = null
onMounted(async () => {
  await store.load()
  await store.pollQuotes()
  await reloadActive()
  lastRefreshAt.value = new Date().toLocaleTimeString('zh-CN')
  // 3s 轮询:快照 + 分时图(若正在看分时)
  pollTimer = setInterval(async () => {
    if (!autoRefresh.value) return
    await store.pollQuotes()
    if (chartTab.value === 'minute') await loadMinute(true)
  }, QUOTE_POLL_MS)
})

onBeforeUnmount(() => {
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
        <span v-if="lastRefreshAt">信号更新于 {{ lastRefreshAt }}</span>
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
                  chartTab === 'minute' ? '当日分钟线,3s 自动更新' : '买卖点为该周期下的策略信号'
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
