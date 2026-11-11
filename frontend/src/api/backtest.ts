import { httpClient } from './client'
import type {
  BacktestResult,
  BatchResultItem,
  Market,
  OptimizeResultItem,
  RunBacktestPayload,
  StrategyMeta,
} from '@/types'

/** 获取全部可用策略 */
export async function listStrategies(): Promise<StrategyMeta[]> {
  const { data } = await httpClient.get<StrategyMeta[]>('/backtest/strategies')
  return data
}

/** 执行回测 */
export async function runBacktest(payload: RunBacktestPayload): Promise<BacktestResult> {
  const { data } = await httpClient.post<BacktestResult>('/backtest/run', payload)
  return data
}

/** 批量回测:同一策略跑多个标的 */
export async function runBatchBacktest(payload: {
  symbols: { market: Market | string; symbol: string }[]
  strategy: string
  params: Record<string, number>
  feeRate: number
}): Promise<BatchResultItem[]> {
  const { data } = await httpClient.post<BatchResultItem[]>('/backtest/batch', payload)
  return data
}

/** 参数寻优:网格扫描,按夏普降序 */
export async function runOptimize(payload: {
  market: Market | string
  symbol: string
  strategy: string
  grid: Record<string, number[]>
  feeRate: number
}): Promise<OptimizeResultItem[]> {
  const { data } = await httpClient.post<OptimizeResultItem[]>('/backtest/optimize', payload)
  return data
}
