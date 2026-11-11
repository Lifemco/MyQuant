<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { extractErrorMessage, httpClient } from '@/api/client'

interface ProviderInfo {
  id: string
  label: string
  enabled: boolean
  markets: string[]
  periods: string[]
  adjustments: string[]
}
const providers = ref<ProviderInfo[]>([])
const downloading = ref(false)
const loadingProviders = ref(true)
function localDate(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}
const form = reactive({
  source: 'akshare',
  market: 'cn',
  symbol: '',
  period: 'day',
  adjustment: 'none',
  startDate: localDate(),
  endDate: localDate(),
  format: 'csv',
})
const selectedProvider = computed(() => providers.value.find((p) => p.id === form.source))
const marketNames: Record<string, string> = { cn: 'A股/指数', hk: '港股', us: '美股' }
const adjustments: Record<string, string> = {
  none: '不复权',
  qfq: '前复权',
  hfq: '后复权',
  yahoo_auto_adjust: 'Yahoo调整价',
}
watch(
  () => form.source,
  () => {
    const provider = selectedProvider.value
    if (!provider) return
    if (!provider.markets.includes(form.market)) form.market = provider.markets[0]
    if (!provider.adjustments.includes(form.adjustment)) form.adjustment = provider.adjustments[0]
  },
)
onMounted(async () => {
  try {
    providers.value = (await httpClient.get<ProviderInfo[]>('/data/providers')).data
    if (!providers.value.some((p) => p.id === form.source && p.enabled))
      form.source = providers.value.find((p) => p.enabled)?.id ?? ''
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    loadingProviders.value = false
  }
})
async function download(): Promise<void> {
  if (!selectedProvider.value?.enabled) {
    ElMessage.warning('请先选择可用数据源')
    return
  }
  if (!form.symbol.trim() || !form.startDate || !form.endDate) {
    ElMessage.warning('请填写代码和完整日期范围')
    return
  }
  if (form.startDate > form.endDate) {
    ElMessage.warning('开始日期不能晚于结束日期')
    return
  }
  downloading.value = true
  try {
    const { format, ...payload } = form
    const response = await httpClient.post(
      '/data/download',
      { ...payload, symbol: payload.symbol.trim() },
      {
        params: { format },
        responseType: 'blob',
        timeout: 120000,
      },
    )
    const match = /filename\*=UTF-8''([^;]+)/i.exec(response.headers['content-disposition'] ?? '')
    const filename = match
      ? decodeURIComponent(match[1])
      : `${form.source}_${form.symbol}.${format}`
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success('行情文件已下载，文件包含来源、复权和成交量单位')
  } catch (error) {
    let message = extractErrorMessage(error)
    if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
      try {
        const body = JSON.parse(await error.response.data.text())
        if (typeof body.detail === 'string') message = body.detail
      } catch {
        /* 保留HTTP错误描述。 */
      }
    }
    ElMessage.error(message)
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <ElCard shadow="never">
    <h2 class="mb-3 text-base font-semibold">行情下载</h2>
    <p class="mb-4 text-sm text-gray-500">
      选择来源和日期下载CSV或JSON，文件保留数据口径。下载用于独立分析，不修改监控中的行情缓存。
    </p>
    <ElForm label-width="100px" :disabled="downloading" @submit.prevent>
      <ElFormItem label="数据源">
        <ElSelect
          v-model="form.source"
          aria-label="下载数据源"
          :loading="loadingProviders"
          :disabled="loadingProviders"
        >
          <ElOption
            v-for="provider in providers"
            :key="provider.id"
            :label="provider.label"
            :value="provider.id"
            :disabled="!provider.enabled"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="市场"
        ><ElSelect v-model="form.market" aria-label="下载市场"
          ><ElOption
            v-for="market in selectedProvider?.markets ?? []"
            :key="market"
            :label="marketNames[market]"
            :value="market" /></ElSelect
      ></ElFormItem>
      <ElFormItem label="代码"
        ><ElInput
          v-model="form.symbol"
          aria-label="下载股票代码"
          placeholder="如600519、sh000001、00700、AAPL"
          class="max-w-sm"
      /></ElFormItem>
      <ElFormItem label="开始日期"
        ><ElInput v-model="form.startDate" type="date" aria-label="下载开始日期" class="max-w-xs"
      /></ElFormItem>
      <ElFormItem label="结束日期"
        ><ElInput v-model="form.endDate" type="date" aria-label="下载结束日期" class="max-w-xs"
      /></ElFormItem>
      <ElFormItem label="周期"
        ><ElSelect v-model="form.period" aria-label="下载周期"
          ><ElOption
            v-for="period in selectedProvider?.periods ?? []"
            :key="period"
            :value="period"
            :label="
              ({ day: '日线', week: '周线', month: '月线' } as Record<string, string>)[period]
            " /></ElSelect
      ></ElFormItem>
      <ElFormItem label="复权"
        ><ElSelect v-model="form.adjustment" aria-label="下载复权"
          ><ElOption
            v-for="adjustment in selectedProvider?.adjustments ?? []"
            :key="adjustment"
            :value="adjustment"
            :label="adjustments[adjustment]" /></ElSelect
      ></ElFormItem>
      <ElFormItem label="文件格式"
        ><ElSelect v-model="form.format" aria-label="下载文件格式"
          ><ElOption label="CSV" value="csv" /><ElOption label="JSON" value="json" /></ElSelect
      ></ElFormItem>
      <ElButton type="primary" :loading="downloading" @click="download">下载行情文件</ElButton>
    </ElForm>
  </ElCard>
</template>
