import { httpClient } from './client'

export type SectionKey = 'trend' | 'industry' | 'distribution' | 'breadth' | 'style' | 'valuation'
export interface IndexSeries {
  code: string
  name: string
  points: { date: string; close: number; amount: number }[]
}
export interface MarketData {
  trend: IndexSeries[]
  industry: { symbol: string; name: string; change: number; size: number }[]
  distribution: {
    bins: { label: string; count: number }[]
    total: number
    valid: number
    excluded: number
    up: number
    flat: number
    down: number
  }
  breadth: {
    total: number
    collected: number
    points: {
      date: string
      ma20: number | null
      ma60: number | null
      eligible20: number
      eligible60: number
    }[]
  }
  style: { baseDate: string; dates: string[]; series: { name: string; values: number[] }[] }
  valuation: {
    name: string
    metric: string
    points: { date: string; pe: number; percentile: number; samples: number }[]
  }
}
export interface MarketSection<T> {
  status: 'ok' | 'partial' | 'stale' | 'unavailable'
  source: string
  asOf: string | null
  fetchedAt: string | null
  notes: string
  error?: string | null
  data: T | null
}
export interface MarketOverview {
  sections: { [K in SectionKey]: MarketSection<MarketData[K]> }
  job: {
    running: boolean
    kind?: string
    done?: number
    total?: number
    failed?: number
    error?: string | null
  }
}
export async function getMarketOverview(): Promise<MarketOverview> {
  return (await httpClient.get<MarketOverview>('/market/overview')).data
}
export async function collectMarket(kind: 'refresh' | 'breadth'): Promise<MarketOverview> {
  return (await httpClient.post<MarketOverview>(`/market/${kind}`)).data
}
