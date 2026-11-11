<script setup lang="ts">
import {
  ElButton,
  ElDivider,
  ElDrawer,
  ElForm,
  ElFormItem,
  ElInputNumber,
  ElMessage,
  ElOption,
  ElSelect,
} from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { listStrategies, runBacktest } from '@/api/backtest'
import { extractErrorMessage } from '@/api/client'
import { updateWatchItem } from '@/api/watchlist'
import EquityCurveChart from '@/components/EquityCurveChart.vue'
import MetricCards from '@/components/MetricCards.vue'
import type { BacktestResult, StrategyMeta, WatchOverviewItem } from '@/types'

const props = defineProps<{
  modelValue: boolean
  item: WatchOverviewItem | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 策略绑定已保存,通知父组件刷新列表与图表 */
  saved: []
  /** 参数编辑中,父组件可用临时参数预览信号 */
  preview: [strategy: string, params: Record<string, number>]
}>()

const drawerVisible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const strategies = ref<StrategyMeta[]>([])
const form = reactive({ strategy: '', params: {} as Record<string, number>, feeRate: 0.0003 })
const saving = ref(false)
const running = ref(false)
const backtestResult = ref<BacktestResult | null>(null)

const currentStrategy = computed(() => strategies.value.find((s) => s.name === form.strategy))

/** 抽屉打开时:加载策略列表,并以该股票当前绑定初始化表单 */
watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible || !props.item) return
    backtestResult.value = null
    if (strategies.value.length === 0) {
      strategies.value = await listStrategies()
    }
    form.strategy = props.item.strategy
    form.params = { ...props.item.params }
  },
)

/** 切换策略时按 schema 重置默认参数 */
watch(
  () => form.strategy,
  (name) => {
    const meta = strategies.value.find((s) => s.name === name)
    if (!meta || !props.item) return
    // 已绑定同策略则保留原参数,否则用默认值
    form.params =
      props.item.strategy === name
        ? { ...props.item.params }
        : Object.fromEntries(Object.entries(meta.paramsSchema).map(([k, s]) => [k, s.default]))
    emit('preview', form.strategy, form.params)
  },
)

function handleParamEdit(): void {
  emit('preview', form.strategy, form.params)
}

async function handleSave(): Promise<void> {
  if (!props.item) return
  saving.value = true
  try {
    await updateWatchItem(props.item.market, props.item.symbol, form.strategy, form.params)
    ElMessage.success('策略绑定已保存')
    emit('saved')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    saving.value = false
  }
}

async function handleRunBacktest(): Promise<void> {
  if (!props.item) return
  running.value = true
  try {
    backtestResult.value = await runBacktest({
      market: props.item.market,
      symbol: props.item.symbol,
      strategy: form.strategy,
      params: form.params,
      feeRate: form.feeRate,
    })
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    running.value = false
  }
}
</script>

<template>
  <ElDrawer v-model="drawerVisible" :title="`策略设置 — ${item?.name ?? ''}`" size="460px">
    <div v-if="item" class="space-y-4">
      <ElForm label-width="90px" label-position="left">
        <ElFormItem label="策略">
          <ElSelect v-model="form.strategy" class="w-full">
            <ElOption v-for="s in strategies" :key="s.name" :value="s.name" :label="s.label" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem
          v-for="(schema, key) in currentStrategy?.paramsSchema ?? {}"
          :key="key"
          :label="schema.desc"
        >
          <ElInputNumber
            v-model="form.params[key]"
            :min="schema.min"
            :max="schema.max"
            :step="schema.type === 'int' ? 1 : 0.5"
            controls-position="right"
            class="w-36"
            @change="handleParamEdit"
          />
        </ElFormItem>
        <ElFormItem label="手续费率">
          <ElInputNumber
            v-model="form.feeRate"
            :min="0"
            :max="0.01"
            :step="0.0001"
            :precision="4"
            controls-position="right"
            class="w-36"
          />
        </ElFormItem>
      </ElForm>

      <div class="flex gap-2">
        <ElButton type="primary" :loading="saving" @click="handleSave">保存绑定</ElButton>
        <ElButton type="warning" :loading="running" @click="handleRunBacktest"> 运行回测 </ElButton>
      </div>

      <template v-if="backtestResult">
        <ElDivider content-position="left">回测结果</ElDivider>
        <MetricCards :metrics="backtestResult.metrics" />
        <div class="mt-3">
          <EquityCurveChart :equity-curve="backtestResult.equityCurve" />
        </div>
      </template>
    </div>
  </ElDrawer>
</template>
