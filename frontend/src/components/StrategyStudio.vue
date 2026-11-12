<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { extractErrorMessage } from '@/api/client'
import {
  draftStrategy,
  executeStrategy,
  getCapabilities,
  getLibrary,
  importFactor,
  preset,
  saveStrategy,
  validateStrategy,
} from '@/api/strategyStudio'
import type {
  AgentDraft,
  Capabilities,
  ExecutionResult,
  SavedStrategy,
  StrategySpec,
} from '@/api/strategyStudio'
import type { SymbolInfo } from '@/types'
import RuleGroupEditor from './RuleGroupEditor.vue'
import EquityCurveChart from './EquityCurveChart.vue'
defineProps<{ symbols: SymbolInfo[] }>()
const spec = ref<StrategySpec>(preset())
const prompt = ref('')
const draft = ref<AgentDraft | null>(null)
const capabilities = ref<Capabilities | null>(null),
  library = ref<SavedStrategy[]>([])
const saved = ref<SavedStrategy | null>(null),
  result = ref<ExecutionResult | null>(null)
const busy = ref(false),
  error = ref(''),
  message = ref(''),
  mode = ref<'form' | 'json'>('form')
const json = ref(JSON.stringify(spec.value, null, 2)),
  selected = ref<string[]>([]),
  fee = ref(0.0003),
  detailIndex = ref(0)
const factorName = ref('pe_ttm'),
  factorSource = ref(''),
  factorTarget = ref(''),
  factorRows = ref('')
let disposed = false
let compiledPrompt: string | null = null
let programmatic = false
const blocked = ref(false)
const detail = computed(() => result.value?.results[detailIndex.value])
watch([selected, fee], () => clearResult(), { deep: true })
function clearResult(): void {
  result.value = null
  message.value = ''
}
watch(
  spec,
  () => {
    clearResult()
    if (mode.value === 'form') json.value = JSON.stringify(spec.value, null, 2)
    if (!programmatic) {
      draft.value = null
      blocked.value = false
      compiledPrompt = null
    }
  },
  { deep: true, flush: 'sync' },
)
watch(prompt, () => {
  if (compiledPrompt !== null && prompt.value !== compiledPrompt) {
    blocked.value = true
    clearResult()
  }
})
watch(json, () => {
  if (mode.value === 'json') clearResult()
})
function choosePreset(type: string): void {
  saved.value = null
  draft.value = null
  blocked.value = false
  compiledPrompt = null
  spec.value = preset(type)
  json.value = JSON.stringify(spec.value, null, 2)
  error.value = ''
}
async function applyJson(): Promise<boolean> {
  try {
    const parsed = await validateStrategy(JSON.parse(json.value))
    if (disposed) return false
    spec.value = parsed
    error.value = ''
    return true
  } catch (err) {
    error.value = extractErrorMessage(err)
    return false
  }
}
async function applyEditorJson(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyJson()
  } finally {
    busy.value = false
  }
}
async function switchMode(value: 'form' | 'json'): Promise<void> {
  if (busy.value || value === mode.value) return
  if (value === 'form') {
    busy.value = true
    try {
      if (!(await applyJson())) return
    } finally {
      busy.value = false
    }
  }
  mode.value = value
}
async function load(): Promise<void> {
  try {
    const [caps, items] = await Promise.all([getCapabilities(), getLibrary()])
    if (disposed) return
    capabilities.value = caps
    library.value = items
  } catch (err) {
    if (!disposed) error.value = extractErrorMessage(err)
  }
}
function loadSaved(event: Event): void {
  const item = library.value.find((i) => i.id === (event.target as HTMLSelectElement).value)
  if (!item) return
  saved.value = item
  compiledPrompt = null
  prompt.value = item.prompt
  draft.value = null
  blocked.value = false
  spec.value = JSON.parse(JSON.stringify(item.spec))
  json.value = JSON.stringify(item.spec, null, 2)
  error.value = ''
}
async function generate(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  clearResult()
  const text = prompt.value
  try {
    const response = await draftStrategy(text)
    if (disposed || prompt.value !== text) return
    draft.value = response
    blocked.value = !response.ready
    compiledPrompt = text
    if (response.spec) {
      programmatic = true
      spec.value = response.spec
      programmatic = false
      json.value = JSON.stringify(response.spec, null, 2)
      saved.value = null
    }
  } catch (err) {
    if (!disposed) error.value = extractErrorMessage(err)
  } finally {
    busy.value = false
  }
}
async function save(copy = false): Promise<void> {
  if (busy.value || blocked.value) return
  busy.value = true
  error.value = ''
  try {
    if (mode.value === 'json' && !(await applyJson())) return
    const item = await saveStrategy({
      ...(saved.value && !copy ? { id: saved.value.id, version: saved.value.version } : {}),
      spec: spec.value,
      prompt: prompt.value,
      summary: draft.value?.summary ?? '',
    })
    if (disposed) return
    saved.value = item
    message.value = `已保存「${item.spec.name}」· 第 ${item.version} 版`
    library.value = await getLibrary()
  } catch (err) {
    if (!disposed) error.value = extractErrorMessage(err)
  } finally {
    busy.value = false
  }
}
async function execute(): Promise<void> {
  if (busy.value || blocked.value) return
  if (!selected.value.length) {
    error.value = '请选择至少一只缓存标的'
    return
  }
  busy.value = true
  error.value = ''
  result.value = null
  try {
    if (mode.value === 'json' && !(await applyJson())) return
    const fingerprint = JSON.stringify(spec.value)
    const response = await executeStrategy(
      spec.value,
      selected.value.map((key) => {
        const [market, symbol] = key.split('/')
        return { market: market!, symbol: symbol! }
      }),
      fee.value,
    )
    if (!disposed && JSON.stringify(spec.value) === fingerprint) {
      result.value = response
      detailIndex.value = 0
    }
  } catch (err) {
    if (!disposed) error.value = extractErrorMessage(err)
  } finally {
    busy.value = false
  }
}
async function readFile(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 3e6) {
    error.value = '因子文件不能超过3MB'
    return
  }
  factorRows.value = await file.text()
}
async function upload(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const [market, symbol] = factorTarget.value.split('/')
    if (!market || !symbol) throw new Error('请选择因子所属标的')
    const text = factorRows.value.trim()
    const observations = text.startsWith('[')
      ? JSON.parse(text)
      : text
          .split(/\r?\n/)
          .filter((line) => line.trim() && !line.startsWith('availableAt'))
          .map((line) => {
            const values = line.split(',')
            if (values.length !== 2 || !values[1]!.trim() || !Number.isFinite(Number(values[1])))
              throw new Error('CSV每行需要 availableAt,value 两列')
            return { availableAt: values[0]!.trim(), value: Number(values[1]) }
          })
    const info = await importFactor({
      market,
      symbol,
      factor: factorName.value,
      source: factorSource.value,
      observations,
    })
    if (disposed) return
    message.value = `已导入 ${info.symbol} / ${info.factor}，${info.rows} 条`
    await load()
  } catch (err) {
    if (!disposed) error.value = extractErrorMessage(err)
  } finally {
    busy.value = false
  }
}
function percent(value?: number): string {
  return value == null ? '—' : `${(value * 100).toFixed(2)}%`
}
function nullable(event: Event): number | null {
  const value = (event.target as HTMLInputElement).value
  return value === '' ? null : Number(value)
}
onMounted(load)
onBeforeUnmount(() => {
  disposed = true
})
</script>
<template>
  <section class="strategy-studio" aria-label="策略创作工作室">
    <div class="studio-heading">
      <div>
        <p>STRATEGY STUDIO</p>
        <h2>把想法，变成可验证的策略</h2>
      </div>
      <span class="model-badge">{{
        capabilities?.configured ? `Agent · ${capabilities.model}` : '模型服务待配置'
      }}</span>
    </div>
    <p class="studio-intro">
      用大白话整理思路，也可以直接组合价格、估值、情绪、事件等条件。执行依据是下方结构化规则，结果为独立回测和最新收盘信号。
    </p>
    <div v-if="error" role="alert" class="studio-alert">{{ error }}</div>
    <div v-if="message" role="status" class="studio-success">{{ message }}</div>
    <div class="studio-columns">
      <section class="agent-panel">
        <h3>01 / 描述你的想法</h3>
        <label for="strategy-prompt">策略想法</label
        ><textarea
          id="strategy-prompt"
          v-model="prompt"
          rows="7"
          :disabled="busy"
          placeholder="例如：20日涨幅超过5%、年化波动率低于40%时买入；涨幅降到0%以下卖出，收盘亏损5%止损，最长持有30个交易日。"
        /><button
          class="primary"
          :disabled="busy || !capabilities?.configured || prompt.trim().length < 2"
          @click="generate"
        >
          {{ busy ? '处理中…' : '让 Agent 整理策略' }}
        </button>
        <p v-if="!capabilities?.configured" class="muted">
          模型地址、名称和密钥由后端配置。配置完成后<a href="#" @click.prevent="load">重新检查</a
          >；现在可以使用右侧条件编辑器。
        </p>
        <div v-if="draft" class="agent-summary">
          <h4>Agent 策略总结</h4>
          <p>{{ draft.summary }}</p>
          <ul v-if="draft.questions.length">
            <li v-for="question in draft.questions" :key="question">待补充：{{ question }}</li>
          </ul>
          <ul v-if="draft.unsupported.length">
            <li v-for="item in draft.unsupported" :key="item">尚不支持：{{ item }}</li>
          </ul>
        </div>
        <p v-if="blocked" class="blocked-note">
          描述尚未形成可执行规则，请补充后重新整理，或明确编辑条件。
        </p>
        <div v-if="!draft && saved?.summary" class="agent-summary">
          <h4>已保存版本的策略总结</h4>
          <p>{{ saved.summary }}</p>
        </div>
        <div class="library-area">
          <h3>我的策略库</h3>
          <select
            aria-label="加载已保存策略"
            :value="saved?.id ?? ''"
            :disabled="busy"
            @change="loadSaved"
          >
            <option value="">选择已保存的策略</option>
            <option v-for="item in library" :key="item.id" :value="item.id">
              {{ item.spec.name }} · v{{ item.version }}
            </option>
          </select>
          <p class="muted">
            {{
              saved
                ? `正在编辑第 ${saved.version} 版；保存将更新该策略。`
                : '新策略；保存后可继续编辑与执行。'
            }}
          </p>
        </div>
      </section>
      <section class="rules-panel">
        <div class="editor-heading">
          <h3>02 / 编辑执行规则</h3>
          <div class="editor-modes">
            <button
              :disabled="busy"
              :class="{ active: mode === 'form' }"
              @click="switchMode('form')"
            >
              条件编辑</button
            ><button
              :disabled="busy"
              :class="{ active: mode === 'json' }"
              @click="switchMode('json')"
            >
              JSON规则
            </button>
          </div>
        </div>
        <div class="presets">
          <span>从示例开始</span
          ><button :disabled="busy" @click="choosePreset('momentum')">动量 / 风险</button
          ><button :disabled="busy" @click="choosePreset('fundamental')">估值 / 情绪</button
          ><button :disabled="busy" @click="choosePreset('cross')">均线交叉</button>
        </div>
        <fieldset :disabled="busy">
          <template v-if="mode === 'form'"
            ><label
              >策略名称<input v-model="spec.name" aria-label="策略名称" maxlength="80" /></label
            ><label>策略说明<input v-model="spec.description" aria-label="策略说明" /></label
            ><RuleGroupEditor v-model="spec.entry" title="入场条件" /><RuleGroupEditor
              v-model="spec.exit"
              title="退出条件" />
            <div class="risk-inputs">
              <label
                >收盘止损（小数）<input
                  :value="spec.stopLossPct ?? ''"
                  type="number"
                  aria-label="收盘止损比例"
                  min="0.001"
                  max="0.99"
                  step=".01"
                  @input="spec.stopLossPct = nullable($event)" /></label
              ><label
                >收盘止盈（小数）<input
                  :value="spec.takeProfitPct ?? ''"
                  type="number"
                  aria-label="收盘止盈比例"
                  min="0.001"
                  max="10"
                  step=".01"
                  @input="spec.takeProfitPct = nullable($event)" /></label
              ><label
                >最长持仓交易日<input
                  :value="spec.maxHoldingBars ?? ''"
                  type="number"
                  aria-label="最长持仓交易日"
                  min="1"
                  max="1000"
                  @input="spec.maxHoldingBars = nullable($event)"
              /></label></div></template
          ><template v-else>
            <textarea
              v-model="json"
              aria-label="策略JSON规则"
              rows="22"
              spellcheck="false"
              class="json-editor"
            /><button @click="applyEditorJson">校验并应用JSON</button></template
          >
        </fieldset>
        <p class="muted">
          收益率、波动率、回撤及风控比例用小数：0.05 =
          5%。退出优先；收盘触发风控，下一交易日开盘执行。每只标的做多或空仓，不进行组合调仓。
        </p>
        <div class="save-actions">
          <button :disabled="busy || blocked" @click="save(false)">保存策略</button
          ><button v-if="saved" :disabled="busy || blocked" @click="save(true)">
            另存为新策略
          </button>
        </div>
      </section>
    </div>
    <details class="factor-import">
      <summary>外部因子数据 · 财务 / 情绪 / 宏观 / 事件</summary>
      <p class="muted">
        导入带真实发布时间的因子值，按当时已知信息匹配；不要填写财报所属期。导入会替换同名因子的完整序列。
      </p>
      <div class="factor-fields">
        <select v-model="factorTarget" aria-label="因子所属标的">
          <option value="">选择标的</option>
          <option
            v-for="item in symbols"
            :key="`${item.market}/${item.symbol}`"
            :value="`${item.market}/${item.symbol}`"
          >
            {{ item.market.toUpperCase() }} {{ item.symbol }}
          </option></select
        ><input
          v-model="factorName"
          aria-label="因子名称"
          placeholder="如 pe_ttm / sentiment"
        /><input
          v-model="factorSource"
          aria-label="因子数据来源"
          placeholder="数据来源 / 计算方法"
        /><input type="file" accept=".csv,.json" aria-label="选择因子数据文件" @change="readFile" />
      </div>
      <textarea
        v-model="factorRows"
        rows="4"
        aria-label="因子发布时间和值"
        placeholder="availableAt,value&#10;2024-01-02T10:00:00+08:00,18.2&#10;2024-04-26T18:00:00+08:00,17.5"
      /><button :disabled="busy" @click="upload">导入因子序列</button>
      <p
        v-for="item in capabilities?.factors ?? []"
        :key="`${item.market}/${item.symbol}/${item.factor}`"
        class="muted"
      >
        {{ item.market }}/{{ item.symbol }} · {{ item.factor }} · {{ item.rows }} 条 ·
        {{ item.source }}
      </p>
    </details>
    <section class="execution-panel">
      <h3>03 / 执行验证</h3>
      <div class="execution-fields">
        <label
          >回测标的（最多20只）<select
            v-model="selected"
            multiple
            aria-label="自定义策略执行标的"
            :disabled="busy"
            size="3"
          >
            <option
              v-for="item in symbols"
              :key="`${item.market}/${item.symbol}`"
              :value="`${item.market}/${item.symbol}`"
            >
              {{ item.market.toUpperCase() }} {{ item.symbol }} · 截至 {{ item.endDate }}
            </option>
          </select></label
        ><label
          >单边手续费率<input
            v-model.number="fee"
            type="number"
            aria-label="自定义策略手续费率"
            min="0"
            max=".01"
            step=".0001"
            :disabled="busy" /></label
        ><button
          class="primary"
          :disabled="busy || blocked || selected.length > 20"
          @click="execute"
        >
          执行回测 / 计算信号
        </button>
      </div>
      <p class="muted">
        使用缓存的已收盘日线。各标的独立计算，不代表真实组合收益；不连接交易账户。
      </p>
      <template v-if="result"
        ><p class="muted">{{ result.execution }}</p>
        <div class="result-table-wrap">
          <table>
            <thead>
              <tr>
                <th>标的</th>
                <th>总收益</th>
                <th>最大回撤</th>
                <th>夏普</th>
                <th>最新目标 / 数据日期</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in result.results" :key="`${item.market}/${item.symbol}`">
                <td>{{ item.symbol }}</td>
                <td>{{ percent(item.metrics?.totalReturn) }}</td>
                <td>{{ percent(item.metrics?.maxDrawdown) }}</td>
                <td>{{ item.metrics?.sharpeRatio?.toFixed(2) ?? '—' }}</td>
                <td>{{ item.error ?? `${item.holding ? '持有' : '空仓'} · ${item.dataAsOf}` }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <select v-model.number="detailIndex" aria-label="查看回测详情标的">
          <option v-for="(item, index) in result.results" :key="index" :value="index">
            {{ item.symbol }}
          </option>
        </select>
        <p v-if="detail?.lastSignal" class="muted">
          最新{{ detail.lastSignal.type === 'buy' ? '买入' : '卖出' }}信号：{{
            detail.lastSignal.date
          }}
          · {{ detail.lastSignal.price }}
        </p>
        <EquityCurveChart
          v-if="detail?.equityCurve"
          :key="detail.symbol"
          :equity-curve="detail.equityCurve"
      /></template>
    </section>
  </section>
</template>
<style scoped>
.strategy-studio {
  border: 1px solid #e0e6ee;
  border-radius: 12px;
  background: white;
  padding: 24px;
  color: #334155;
}
.studio-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.studio-heading p {
  font-size: 10px;
  letter-spacing: 0.15em;
  color: #d23a47;
  margin: 0 0 8px;
}
.studio-heading h2 {
  font-size: 21px;
  font-weight: 650;
  margin: 0;
}
.model-badge {
  font-size: 10px;
  align-self: flex-start;
  color: #7c8797;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  padding: 6px 10px;
}
.studio-intro {
  font-size: 12px;
  line-height: 1.9;
  color: #7b8798;
  margin: 12px 0 24px;
}
.studio-columns {
  display: grid;
  grid-template-columns: minmax(230px, 0.75fr) minmax(0, 1.5fr);
  gap: 24px;
}
.agent-panel {
  background: #fafbfc;
  border-radius: 8px;
  padding: 18px;
}
.agent-panel h3,
.rules-panel h3,
.execution-panel h3 {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 14px;
}
label {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 10px;
}
input,
textarea,
select {
  display: block;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #dce2eb;
  border-radius: 6px;
  color: #334155;
  background: white;
  padding: 9px;
  margin-top: 5px;
  font-size: 12px;
  min-width: 0;
}
textarea {
  resize: vertical;
  line-height: 1.8;
}
button {
  border: 1px solid #dce2eb;
  background: white;
  border-radius: 6px;
  color: #64748b;
  padding: 8px 11px;
  cursor: pointer;
  font-size: 11px;
}
button.primary {
  background: #d63642;
  border-color: #d63642;
  color: white;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
.agent-panel > button {
  width: 100%;
  margin-top: 10px;
}
.muted {
  font-size: 10px;
  color: #8a95a5;
  line-height: 1.8;
  margin: 10px 0;
  overflow-wrap: anywhere;
}
.muted a {
  color: #d63642;
}
.agent-summary {
  font-size: 12px;
  line-height: 1.9;
  margin-top: 18px;
  white-space: pre-wrap;
}
.agent-summary h4 {
  font-weight: 600;
}
.agent-summary li {
  color: #a16207;
}
.blocked-note {
  font-size: 11px;
  color: #b45309;
}
.library-area {
  border-top: 1px solid #e5eaf0;
  margin-top: 24px;
  padding-top: 18px;
}
.editor-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.editor-modes {
  display: flex;
}
.editor-modes button {
  border: 0;
}
.editor-modes button.active {
  background: #fff1f2;
  color: #d63642;
}
.presets {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  margin: 0 0 14px;
}
.presets span {
  font-size: 10px;
  color: #9aa4b3;
}
.presets button {
  padding: 5px 8px;
  font-size: 10px;
}
fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.risk-inputs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.json-editor {
  font-family: ui-monospace, monospace;
  font-size: 11px;
}
.save-actions {
  display: flex;
  gap: 8px;
}
.factor-import,
.execution-panel {
  border-top: 1px solid #e7ebf1;
  padding-top: 20px;
  margin-top: 24px;
}
.factor-import summary {
  cursor: pointer;
  color: #64748b;
  font-size: 12px;
}
.factor-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.factor-import textarea {
  margin: 12px 0;
}
.execution-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px auto;
  gap: 12px;
  align-items: center;
}
.execution-fields button {
  margin-top: 8px;
}
.result-table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  text-align: left;
  font-size: 11px;
  border-collapse: collapse;
}
th,
td {
  padding: 10px;
  border-bottom: 1px solid #edf0f4;
  white-space: nowrap;
}
.studio-alert,
.studio-success {
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
  margin-bottom: 14px;
  background: #fff7ed;
  color: #9a3412;
  overflow-wrap: anywhere;
}
.studio-success {
  background: #ecfdf5;
  color: #047857;
}
@media (max-width: 1100px) {
  .studio-columns {
    grid-template-columns: 1fr;
  }
  .execution-fields {
    grid-template-columns: 1fr 130px;
  }
  .execution-fields button {
    grid-column: 1 / -1;
  }
}
@media (max-width: 620px) {
  .strategy-studio {
    padding: 14px;
  }
  .studio-heading h2 {
    font-size: 18px;
  }
  .agent-panel {
    padding: 12px;
  }
  .risk-inputs,
  .factor-fields,
  .execution-fields {
    grid-template-columns: 1fr;
  }
  .editor-heading {
    flex-wrap: wrap;
  }
}
</style>
