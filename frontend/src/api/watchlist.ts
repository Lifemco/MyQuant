import { httpClient } from './client'
import type { Market, WatchItem, WatchOverviewItem } from '@/types'

/** 自选股列表 */
export async function listWatchItems(): Promise<WatchItem[]> {
  const { data } = await httpClient.get<WatchItem[]>('/watchlist')
  return data
}

/** 添加自选股(后端自动抓取行情并补全名称) */
export async function addWatchItem(market: Market, symbol: string): Promise<WatchItem> {
  const { data } = await httpClient.post<WatchItem>('/watchlist', { market, symbol })
  return data
}

/** 更新自选股绑定的策略与参数 */
export async function updateWatchItem(
  market: Market,
  symbol: string,
  strategy: string,
  params: Record<string, number>,
): Promise<WatchItem> {
  const { data } = await httpClient.put<WatchItem>(`/watchlist/${market}/${symbol}`, {
    strategy,
    params,
  })
  return data
}

/** 删除自选股 */
export async function removeWatchItem(market: Market, symbol: string): Promise<void> {
  await httpClient.delete(`/watchlist/${market}/${symbol}`)
}

/** 自选列表实时总览(信号 + 最新行情) */
export async function getOverview(): Promise<WatchOverviewItem[]> {
  const { data } = await httpClient.get<WatchOverviewItem[]>('/monitor/overview')
  return data
}

/** 刷新全部自选行情后返回总览 */
export async function refreshOverview(): Promise<WatchOverviewItem[]> {
  const { data } = await httpClient.post<WatchOverviewItem[]>('/monitor/refresh')
  return data
}
