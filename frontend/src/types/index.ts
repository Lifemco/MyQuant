/** 市场代码 */
export type Market = 'cn' | 'hk' | 'us'

/** K线数据点 */
export interface BarPoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/** 已缓存标的信息 */
export interface SymbolInfo {
  market: string
  symbol: string
  rows: number
  startDate: string | null
  endDate: string | null
}

/** 策略参数说明 */
export interface ParamSchema {
  type: 'int' | 'float'
  default: number
  min: number
  max: number
  desc: string
}

/** 策略元信息 */
export interface StrategyMeta {
  name: string
  label: string
  /** 策略说明(来源/口径) */
  desc?: string
  paramsSchema: Record<string, ParamSchema>
}

/** 回测绩效指标 */
export interface BacktestMetrics {
  totalReturn: number
  annualReturn: number
  annualVolatility: number
  sharpeRatio: number
  maxDrawdown: number
  calmarRatio: number
  totalTrades: number
  winRate: number
}

/** 净值曲线点 */
export interface EquityPoint {
  date: string
  equity: number
}

/** 单笔交易记录 */
export interface Trade {
  entryDate: string
  exitDate: string | null
  pnlPct: number
  entryPrice?: number | null
  exitPrice?: number | null
}

/** 回测结果 */
export interface BacktestResult {
  metrics: BacktestMetrics
  equityCurve: EquityPoint[]
  trades: Trade[]
  bars: BarPoint[]
}

/** 抓取行情请求 */
export interface FetchBarsPayload {
  market: Market
  symbol: string
  startDate: string
  endDate: string
}

/** 回测请求 */
export interface RunBacktestPayload {
  market: Market
  symbol: string
  strategy: string
  params: Record<string, number>
  feeRate: number
}

/** 自选股条目 */
export interface WatchItem {
  market: Market
  symbol: string
  name: string
  strategy: string
  params: Record<string, number>
}

/** 买卖点标记 */
export interface SignalMarker {
  date: string
  type: 'buy' | 'sell'
  price: number
}

/** 自选列表行:条目 + 实时状态 */
export interface WatchOverviewItem extends WatchItem {
  dataAsOf?: string | null
  signalAsOf?: string | null
  error?: string | null
  refreshError?: string | null
  refreshedAt?: string | null
  holding: boolean
  lastSignal: SignalMarker | null
  close: number | null
  changePct: number | null
}

/** K线 + 信号图数据 */
export interface ChartData {
  signalAsOf?: string | null
  bars: BarPoint[]
  markers: SignalMarker[]
  holding: boolean
  lastSignal: SignalMarker | null
}

/** K线图请求 */
export interface ChartPayload {
  market: Market
  symbol: string
  strategy: string
  params: Record<string, number>
  period?: Period
}

/** K线周期 */
export type Period = 'day' | 'week' | 'month'

/** 行情快照(同花顺行情面板) */
export interface QuoteSnapshot {
  market: string
  symbol: string
  name: string
  price: number | null
  prevClose: number | null
  open: number | null
  high: number | null
  low: number | null
  volume: number | null
  amount: number | null
  change: number | null
  changePct: number | null
  turnoverRate: number | null
  peRatio: number | null
  amplitude: number | null
  circulatingMarketCap: number | null
  totalMarketCap: number | null
  pbRatio: number | null
  time: string
}

/** 分时点 */
export interface MinutePoint {
  time: string
  price: number
  avg: number
  volume: number
}

/** 当日分时数据 */
export interface MinuteData {
  market: string
  symbol: string
  date: string
  prevClose: number | null
  points: MinutePoint[]
}

/** 批量回测单项结果 */
export interface BatchResultItem {
  market: string
  symbol: string
  metrics: BacktestMetrics | null
  error: string | null
}

/** 参数寻优单项结果 */
export interface OptimizeResultItem {
  params: Record<string, number>
  metrics: BacktestMetrics
}
