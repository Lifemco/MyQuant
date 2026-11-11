import { httpClient } from './client'
import type { ChartData, ChartPayload, Market, MinuteData, QuoteSnapshot } from '@/types'

/** 获取单票 K线 + 买卖点标记(可传临时策略参数预览) */
export async function getChartData(payload: ChartPayload): Promise<ChartData> {
  const { data } = await httpClient.post<ChartData>('/monitor/chart', payload)
  return data
}

/** 批量行情快照(3s 轮询用) */
export async function getQuotes(
  items: { market: Market | string; symbol: string }[],
): Promise<QuoteSnapshot[]> {
  const { data } = await httpClient.post<QuoteSnapshot[]>('/monitor/quotes', { items })
  return data
}

/** 当日分时数据 */
export async function getMinuteData(market: string, symbol: string): Promise<MinuteData> {
  const { data } = await httpClient.get<MinuteData>(`/monitor/minute/${market}/${symbol}`)
  return data
}
