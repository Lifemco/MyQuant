<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { httpClient, extractErrorMessage } from '@/api/client'
import { listStrategies, runBatchBacktest, runOptimize } from '@/api/backtest'
import DataDownloadCard from '@/components/DataDownloadCard.vue'
import StrategyStudio from '@/components/StrategyStudio.vue'
import type { BatchResultItem, OptimizeResultItem, StrategyMeta, SymbolInfo } from '@/types'

const strategies = ref<StrategyMeta[]>([])
const symbols = ref<SymbolInfo[]>([])
const strategy = ref('sma_cross')
const selected = ref<string[]>([])
const params = reactive<Record<string, number>>({})
const candidates = reactive<Record<string, string>>({})
const feeRate = ref(0.0003)
const busy = ref(false)
const batchResults = ref<BatchResultItem[]>([])
const optimizeResults = ref<OptimizeResultItem[]>([])
const meta = computed(() => strategies.value.find((s) => s.name === strategy.value))
function defaults(): void {
  for (const key of Object.keys(params)) delete params[key]
  for (const key of Object.keys(candidates)) delete candidates[key]
  for (const [key, value] of Object.entries(meta.value?.paramsSchema ?? {})) {
    params[key] = value.default
    candidates[key] = String(value.default)
  }
  batchResults.value = []
  optimizeResults.value = []
}
watch(strategy, defaults)
onMounted(async () => {
  try {
    const [metas, cached] = await Promise.all([
      listStrategies(),
      httpClient.get<SymbolInfo[]>('/data/symbols'),
    ])
    strategies.value = metas
    symbols.value = cached.data
    defaults()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
})
async function run(mode: 'batch' | 'optimize'): Promise<void> {
  if (!selected.value.length) {
    ElMessage.warning('请选择已缓存行情的股票')
    return
  }
  busy.value = true
  batchResults.value = []
  optimizeResults.value = []
  try {
    if (mode === 'batch') {
      batchResults.value = await runBatchBacktest({
        symbols: selected.value.map((key) => {
          const [market, symbol] = key.split('/')
          return { market, symbol }
        }),
        strategy: strategy.value,
        params: { ...params },
        feeRate: feeRate.value,
      })
    } else {
      if (selected.value.length !== 1) throw new Error('参数寻优请只选择一只股票')
      const grid = Object.fromEntries(
        Object.entries(candidates).map(([key, text]) => {
          const parts = text.split(/[,，]/).map((v) => v.trim())
          const values = parts.map(Number)
          if (parts.some((v) => !v) || values.some((v) => !Number.isFinite(v)))
            throw new Error('候选值请使用逗号分隔的数字')
          return [key, values]
        }),
      )
      const [market, symbol] = selected.value[0].split('/')
      optimizeResults.value = await runOptimize({
        market,
        symbol,
        strategy: strategy.value,
        grid,
        feeRate: feeRate.value,
      })
    }
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    busy.value = false
  }
}
function percent(value?: number): string {
  return value == null ? '--' : `${(value * 100).toFixed(2)}%`
}
</script>

<template>
  <main class="strategy-page mx-auto w-full max-w-7xl space-y-4 p-6">
    <h1 class="text-xl font-bold">策略中心</h1>
    <p class="text-sm text-gray-500">
      使用已缓存的日线比较策略。收盘产生信号，下一交易日开盘执行；胜率仅统计已平仓交易。
    </p>
    <StrategyStudio :symbols="symbols" />
    <h2 class="text-base font-semibold text-gray-700">内置策略实验室</h2>
    <ElCard shadow="never">
      <ElForm label-width="130px" :disabled="busy">
        <ElFormItem label="股票（最多20只）">
          <ElSelect
            v-model="selected"
            multiple
            :multiple-limit="20"
            class="w-full"
            placeholder="请先在行情监控添加股票并刷新行情"
          >
            <ElOption
              v-for="item in symbols"
              :key="`${item.market}/${item.symbol}`"
              :value="`${item.market}/${item.symbol}`"
              :label="`${item.market.toUpperCase()} ${item.symbol} · 截至 ${item.endDate}`"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="策略">
          <ElSelect v-model="strategy"
            ><ElOption
              v-for="item in strategies"
              :key="item.name"
              :value="item.name"
              :label="item.label"
          /></ElSelect>
        </ElFormItem>
        <p class="mb-4 text-sm text-gray-500">{{ meta?.desc }}</p>
        <ElFormItem
          v-for="(schema, key) in meta?.paramsSchema ?? {}"
          :key="key"
          :label="schema.desc"
        >
          <ElInputNumber
            v-model="params[key]"
            :min="schema.min"
            :max="schema.max"
            :step="schema.type === 'int' ? 1 : 0.5"
          />
          <ElInput
            v-model="candidates[key]"
            class="ml-4 max-w-64"
            placeholder="寻优候选值，如 3,5,10"
            :aria-label="`${schema.desc}候选值`"
          />
        </ElFormItem>
        <ElFormItem label="单边手续费率"
          ><ElInputNumber v-model="feeRate" :min="0" :max="0.01" :step="0.0001" :precision="4"
        /></ElFormItem>
      </ElForm>
      <div class="flex gap-3">
        <ElButton type="primary" :loading="busy" @click="run('batch')">批量回测</ElButton>
        <ElButton :disabled="busy" @click="run('optimize')">参数寻优（最多200组）</ElButton>
      </div>
      <p class="mt-3 text-xs text-gray-500">
        寻优使用右侧候选值；结果属于样本内比较，不代表未来收益。
      </p>
    </ElCard>
    <ElCard v-if="batchResults.length" shadow="never">
      <ElTable :data="batchResults">
        <ElTableColumn prop="symbol" label="股票" />
        <ElTableColumn label="总收益"
          ><template #default="{ row }">{{
            percent(row.metrics?.totalReturn)
          }}</template></ElTableColumn
        >
        <ElTableColumn label="最大回撤"
          ><template #default="{ row }">{{
            percent(row.metrics?.maxDrawdown)
          }}</template></ElTableColumn
        >
        <ElTableColumn label="夏普"
          ><template #default="{ row }">{{
            row.metrics?.sharpeRatio ?? '--'
          }}</template></ElTableColumn
        >
        <ElTableColumn prop="error" label="状态" />
      </ElTable>
    </ElCard>
    <ElCard v-if="optimizeResults.length" shadow="never">
      <ElTable :data="optimizeResults">
        <ElTableColumn label="参数"
          ><template #default="{ row }">{{
            Object.entries(row.params)
              .map(([k, v]) => `${k}=${v}`)
              .join('，')
          }}</template></ElTableColumn
        >
        <ElTableColumn label="总收益"
          ><template #default="{ row }">{{
            percent(row.metrics.totalReturn)
          }}</template></ElTableColumn
        >
        <ElTableColumn prop="metrics.sharpeRatio" label="夏普（降序）" />
      </ElTable>
    </ElCard>
    <DataDownloadCard />
  </main>
</template>

<style scoped>
@media (max-width: 760px) {
  .strategy-page {
    padding: 16px 10px;
  }
}
</style>
