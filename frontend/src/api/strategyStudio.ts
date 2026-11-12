import { httpClient } from './client'
import type { BacktestMetrics, EquityPoint, SignalMarker, SymbolInfo } from '@/types'
export type OperandKind =
  | 'constant'
  | 'close'
  | 'open'
  | 'high'
  | 'low'
  | 'volume'
  | 'sma'
  | 'rsi'
  | 'return'
  | 'volatility'
  | 'drawdown'
  | 'volume_ratio'
  | 'external'
export interface Operand {
  kind: OperandKind
  value?: number | null
  window?: number
  factor?: string | null
  maxAgeDays?: number
}
export interface Condition {
  left: Operand
  op: 'gt' | 'gte' | 'lt' | 'lte' | 'cross_above' | 'cross_below'
  right: Operand
}
export interface RuleGroup {
  logic: 'all' | 'any'
  conditions: Condition[]
}
export interface StrategySpec {
  name: string
  description: string
  entry: RuleGroup
  exit: RuleGroup
  stopLossPct: number | null
  takeProfitPct: number | null
  maxHoldingBars: number | null
}
export interface AgentDraft {
  summary: string
  spec: StrategySpec | null
  questions: string[]
  unsupported: string[]
  ready: boolean
}
export interface FactorInfo {
  market: string
  symbol: string
  factor: string
  source: string
  rows: number
}
export interface Capabilities {
  configured: boolean
  model: string | null
  factors: FactorInfo[]
  execution: string
}
export interface SavedStrategy {
  id: string
  version: number
  spec: StrategySpec
  prompt: string
  summary: string
}
export interface StudioResult {
  market: string
  symbol: string
  error?: string
  metrics?: BacktestMetrics
  equityCurve?: EquityPoint[]
  dataAsOf?: string
  holding?: boolean
  lastSignal?: SignalMarker | null
}
export interface ExecutionResult {
  execution: string
  spec: StrategySpec
  results: StudioResult[]
}
export const operandOptions: { value: OperandKind; label: string }[] = [
  { value: 'close', label: '收盘价' },
  { value: 'open', label: '开盘价' },
  { value: 'high', label: '最高价' },
  { value: 'low', label: '最低价' },
  { value: 'volume', label: '成交量' },
  { value: 'constant', label: '固定数值' },
  { value: 'sma', label: 'N日均价' },
  { value: 'rsi', label: 'N日RSI' },
  { value: 'return', label: 'N日收益率' },
  { value: 'volatility', label: '年化波动率' },
  { value: 'drawdown', label: 'N日回撤' },
  { value: 'volume_ratio', label: '相对前N日量比' },
  { value: 'external', label: '外部因子' },
]
export function constant(value: number): Operand {
  return { kind: 'constant', value }
}
export function preset(type = 'momentum'): StrategySpec {
  const condition = (left: Operand, op: Condition['op'], right: Operand): Condition => ({
    left,
    op,
    right,
  })
  const entry =
    type === 'fundamental'
      ? [
          condition({ kind: 'external', factor: 'pe_ttm', maxAgeDays: 90 }, 'lt', constant(20)),
          condition({ kind: 'external', factor: 'sentiment', maxAgeDays: 7 }, 'gt', constant(0.3)),
        ]
      : type === 'cross'
        ? [condition({ kind: 'sma', window: 5 }, 'cross_above', { kind: 'sma', window: 20 })]
        : [
            condition({ kind: 'return', window: 20 }, 'gt', constant(0.05)),
            condition({ kind: 'volatility', window: 20 }, 'lt', constant(0.4)),
          ]
  const exit =
    type === 'fundamental'
      ? [
          condition({ kind: 'external', factor: 'pe_ttm', maxAgeDays: 90 }, 'gt', constant(30)),
          condition({ kind: 'external', factor: 'sentiment', maxAgeDays: 7 }, 'lt', constant(0)),
        ]
      : type === 'cross'
        ? [condition({ kind: 'sma', window: 5 }, 'cross_below', { kind: 'sma', window: 20 })]
        : [condition({ kind: 'return', window: 20 }, 'lt', constant(0))]
  return {
    name:
      type === 'fundamental'
        ? '估值与情绪条件策略'
        : type === 'cross'
          ? '自定义双均线'
          : '动量与波动率策略',
    description: '可修改条件、阈值和风控；按日收盘计算。',
    entry: { logic: 'all', conditions: entry },
    exit: { logic: 'any', conditions: exit },
    stopLossPct: 0.05,
    takeProfitPct: 0.15,
    maxHoldingBars: 30,
  }
}
export async function validateStrategy(payload: unknown): Promise<StrategySpec> {
  return (await httpClient.post('/strategies/validate', payload)).data
}
export async function getCapabilities(): Promise<Capabilities> {
  return (await httpClient.get('/strategies/capabilities')).data
}
export async function getLibrary(): Promise<SavedStrategy[]> {
  return (await httpClient.get('/strategies/library')).data
}
export async function draftStrategy(prompt: string): Promise<AgentDraft> {
  return (await httpClient.post('/strategies/draft', { prompt })).data
}
export async function saveStrategy(payload: {
  id?: string
  version?: number
  spec: StrategySpec
  prompt: string
  summary: string
}): Promise<SavedStrategy> {
  return (await httpClient.post('/strategies/library', payload)).data
}
export async function executeStrategy(
  spec: StrategySpec,
  symbols: Pick<SymbolInfo, 'market' | 'symbol'>[],
  feeRate: number,
): Promise<ExecutionResult> {
  return (await httpClient.post('/strategies/execute', { spec, symbols, feeRate })).data
}
export async function importFactor(payload: {
  market: string
  symbol: string
  factor: string
  source: string
  observations: { availableAt: string; value: number }[]
}): Promise<FactorInfo> {
  return (await httpClient.post('/strategies/factors', payload)).data
}
