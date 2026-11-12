<script setup lang="ts">
import { ElTable, ElTableColumn, ElTag } from 'element-plus'
import { computed, onBeforeUnmount, ref } from 'vue'

import type { SignalMarker } from '@/types'

const props = defineProps<{
  markers: SignalMarker[]
  holding: boolean
  lastSignal: SignalMarker | null
  priceUnit?: string
  currency?: string
  /** 面板整体高度(px),由父级拖拽控制 */
  height?: number
}>()

/** 历史信号倒序展示(最新在前) */
const history = computed(() => [...props.markers].reverse())

/** 表格高度 = 面板高度 - 卡片边框与内边距 */
const media = window.matchMedia('(max-width: 760px)')
const compact = ref(media.matches)
function resizePanel(): void {
  compact.value = media.matches
}
media.addEventListener('change', resizePanel)
onBeforeUnmount(() => media.removeEventListener('change', resizePanel))
const tableHeight = computed(() => Math.max(60, (props.height ?? 150) - (compact.value ? 110 : 20)))

/** 表格行辅助:ElTable 插槽行类型宽松,断言收敛在 script 内 */
function tagType(row: unknown): 'danger' | 'success' {
  return (row as SignalMarker).type === 'buy' ? 'danger' : 'success'
}

function typeLabel(row: unknown): string {
  return (row as SignalMarker).type === 'buy' ? '买入' : '卖出'
}

function formatPrice(price: number): string {
  if (props.priceUnit === 'point') return `${price}点`
  const prefix = props.currency === 'USD' ? '$' : props.currency === 'HKD' ? 'HK$' : '¥'
  return `${prefix}${price}`
}
function fmtPrice(row: unknown): string {
  return formatPrice((row as SignalMarker).price)
}
</script>

<template>
  <!-- 高度跟随面板:状态卡拉伸,历史表高度自适应 -->
  <div class="signal-layout flex h-full items-stretch gap-3">
    <div
      class="signal-state flex h-full w-56 shrink-0 items-center justify-between rounded border px-3"
      :class="holding ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-gray-50'"
    >
      <div>
        <div class="text-xs text-gray-500">已确认日线信号(T+1执行)</div>
        <div class="mt-0.5 text-xl font-bold" :class="holding ? 'text-red-500' : 'text-gray-500'">
          {{ holding ? '目标持仓' : '目标空仓' }}
        </div>
      </div>
      <div v-if="lastSignal" class="text-right text-xs">
        <ElTag :type="lastSignal.type === 'buy' ? 'danger' : 'success'" size="small" effect="dark">
          {{ lastSignal.type === 'buy' ? '买入' : '卖出' }}
        </ElTag>
        <div class="mt-1 text-gray-500">{{ lastSignal.date }}</div>
        <div class="text-gray-500">@ {{ formatPrice(lastSignal.price) }}</div>
      </div>
      <div v-else class="text-xs text-gray-400">暂无信号</div>
    </div>

    <div class="min-w-0 flex-1">
      <ElTable :data="history" size="small" :height="tableHeight" empty-text="暂无信号">
        <ElTableColumn prop="date" label="日期" width="120" />
        <ElTableColumn label="操作" width="80">
          <template #default="{ row }">
            <ElTag :type="tagType(row)" size="small" effect="dark">
              {{ typeLabel(row) }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="触发价">
          <template #default="{ row }">{{ fmtPrice(row) }}</template>
        </ElTableColumn>
      </ElTable>
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 760px) {
  .signal-layout {
    flex-direction: column;
    gap: 8px;
  }
  .signal-state {
    width: 100%;
    height: 72px;
    box-sizing: border-box;
  }
  .signal-state > div:first-child {
    min-width: 0;
    padding-right: 10px;
  }
  .signal-state :deep(.text-xl) {
    font-size: 17px;
  }
}
</style>
