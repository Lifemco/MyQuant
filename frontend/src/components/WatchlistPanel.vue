<script setup lang="ts">
import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElMessage,
  ElOption,
  ElPopconfirm,
  ElSelect,
  ElTag,
  ElTooltip,
} from 'element-plus'
import { computed, reactive, ref } from 'vue'

import { addWatchItem, removeWatchItem } from '@/api/watchlist'
import { extractErrorMessage } from '@/api/client'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Market } from '@/types'

const store = useWatchlistStore()

const MARKET_OPTIONS: { value: Market; label: string; placeholder: string }[] = [
  { value: 'cn', label: 'A股', placeholder: '如 600519' },
  { value: 'hk', label: '港股', placeholder: '如 00700' },
  { value: 'us', label: '美股', placeholder: '如 AAPL' },
]

const addDialogVisible = ref(false)
const addForm = reactive({ market: 'cn' as Market, symbol: '' })
const adding = ref(false)

const addPlaceholder = computed(
  () => MARKET_OPTIONS.find((m) => m.value === addForm.market)?.placeholder ?? '',
)

async function handleAdd(): Promise<void> {
  if (!addForm.symbol.trim()) {
    ElMessage.warning('请输入股票代码')
    return
  }
  adding.value = true
  try {
    const item = await addWatchItem(addForm.market, addForm.symbol.trim())
    ElMessage.success(`已添加:${item.name}`)
    addDialogVisible.value = false
    addForm.symbol = ''
    await store.load()
    store.select(item.market, item.symbol)
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    adding.value = false
  }
}

async function handleRemove(market: Market, symbol: string): Promise<void> {
  try {
    await removeWatchItem(market, symbol)
    await store.load()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
}

/** 涨跌幅显示,A股习惯:涨红跌绿 */
function changeClass(changePct: number | null): string {
  if (changePct === null) return 'text-gray-400'
  return changePct >= 0 ? 'text-red-500' : 'text-green-600'
}

function fmtChange(changePct: number | null): string {
  if (changePct === null) return '--'
  return `${changePct >= 0 ? '+' : ''}${(changePct * 100).toFixed(2)}%`
}
</script>

<template>
  <div class="flex flex-col">
    <div class="flex items-center justify-between border-b border-gray-200 p-3">
      <span class="font-medium text-gray-700">自选股监控</span>
      <ElButton type="primary" size="small" @click="addDialogVisible = true">+ 添加</ElButton>
    </div>

    <!-- 列表随页面自然延伸,整页滚动 -->
    <div>
      <ElEmpty v-if="store.items.length === 0" description="添加股票开始监控" :image-size="80" />
      <div
        v-for="item in store.items"
        :key="store.keyOf(item.market, item.symbol)"
        class="group cursor-pointer border-b border-gray-100 p-3 transition-colors hover:bg-blue-50"
        :class="{
          'bg-blue-50 border-l-2 border-l-blue-500':
            store.selectedKey === store.keyOf(item.market, item.symbol),
        }"
        @click="store.select(item.market, item.symbol)"
      >
        <div class="flex items-center justify-between">
          <div>
            <span class="font-medium text-gray-800">{{ item.name }}</span>
            <span class="ml-1 text-xs text-gray-400">{{ item.symbol }}</span>
          </div>
          <!-- 悬停行才显示删除按钮 -->
          <ElPopconfirm title="移出自选?" @confirm="handleRemove(item.market, item.symbol)">
            <template #reference>
              <ElButton
                size="small"
                link
                type="danger"
                class="opacity-0 transition-opacity group-hover:opacity-100"
                @click.stop
                >删除</ElButton
              >
            </template>
          </ElPopconfirm>
        </div>
        <div class="mt-1 flex items-center justify-between text-sm">
          <span
            :class="
              changeClass(store.quoteOf(item.market, item.symbol)?.changePct ?? item.changePct)
            "
            class="font-semibold"
          >
            {{ store.quoteOf(item.market, item.symbol)?.price ?? item.close ?? '--' }}
            <span class="text-xs">
              {{ fmtChange(store.quoteOf(item.market, item.symbol)?.changePct ?? item.changePct) }}
            </span>
          </span>
          <!-- 策略信号标签:悬停显示含义说明 -->
          <ElTooltip
            v-if="item.lastSignal"
            :content="`策略「${item.strategy}」最近信号:${item.lastSignal.type === 'buy' ? '买入' : '卖出'}(${item.lastSignal.date} @ ¥${item.lastSignal.price}),T+1 开盘手动执行,仅供参考`"
            placement="top"
          >
            <ElTag
              :type="item.lastSignal.type === 'buy' ? 'danger' : 'success'"
              size="small"
              effect="dark"
            >
              信号·{{ item.lastSignal.type === 'buy' ? '买入' : '卖出' }}
              {{ item.lastSignal.date.slice(5) }}
            </ElTag>
          </ElTooltip>
          <ElTag v-else size="small" type="info">无信号</ElTag>
        </div>
        <div class="mt-1 text-xs text-gray-400">
          {{ item.holding ? '● 目标持仓' : '○ 目标空仓' }}
          <span v-if="item.error || item.refreshError" class="text-amber-600">
            · {{ item.refreshError || item.error }}</span
          >
        </div>
      </div>
    </div>

    <ElDialog v-model="addDialogVisible" title="添加自选股" width="380px">
      <ElForm label-width="60px" @submit.prevent>
        <ElFormItem label="市场">
          <ElSelect v-model="addForm.market" class="w-full">
            <ElOption
              v-for="m in MARKET_OPTIONS"
              :key="m.value"
              :value="m.value"
              :label="m.label"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="代码">
          <ElInput
            v-model="addForm.symbol"
            :placeholder="addPlaceholder"
            clearable
            @keyup.enter="handleAdd"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="addDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="adding" @click="handleAdd">添加(自动抓取行情)</ElButton>
      </template>
    </ElDialog>
  </div>
</template>
