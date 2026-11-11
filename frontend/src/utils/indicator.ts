/** 技术指标计算:MA / EMA / MACD,输入收盘价序列,输出与输入等长 */

/** 简单移动平均,前 window-1 位为 null */
export function computeMA(values: number[], window: number): (number | null)[] {
  const result: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= window) sum -= values[i - window]
    result.push(i >= window - 1 ? round2(sum / window) : null)
  }
  return result
}

/** 指数移动平均(EMA),首日以收盘起算 */
export function computeEMA(values: number[], window: number): number[] {
  const k = 2 / (window + 1)
  const result: number[] = []
  let prev = values[0] ?? 0
  for (const v of values) {
    prev = v * k + prev * (1 - k)
    result.push(prev)
  }
  return result
}

export interface MacdResult {
  dif: number[]
  dea: number[]
  macd: (number | null)[]
}

/** MACD(12, 26, 9),红柱 = 2*(DIF-DEA) */
export function computeMACD(values: number[]): MacdResult {
  if (values.length === 0) return { dif: [], dea: [], macd: [] }
  const ema12 = computeEMA(values, 12)
  const ema26 = computeEMA(values, 26)
  const dif = ema12.map((v, i) => round2(v - ema26[i]))
  const dea = computeEMA(dif, 9).map(round2)
  const macd = dif.map((v, i) => round2(2 * (v - dea[i])))
  return { dif, dea, macd }
}

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

export interface KdjResult {
  k: (number | null)[]
  d: (number | null)[]
  j: (number | null)[]
}

/** KDJ(9,3,3):RSV=(C-LLV9)/(HHV9-LLV9)*100,K/D 为 α=1/3 的平滑,J=3K-2D */
export function computeKDJ(highs: number[], lows: number[], closes: number[], n = 9): KdjResult {
  const len = closes.length
  const k: (number | null)[] = []
  const d: (number | null)[] = []
  const j: (number | null)[] = []
  // 初值按惯例取 50
  let prevK = 50
  let prevD = 50
  for (let i = 0; i < len; i++) {
    if (i < n - 1) {
      k.push(null)
      d.push(null)
      j.push(null)
      continue
    }
    let hh = -Infinity
    let ll = Infinity
    for (let m = i - n + 1; m <= i; m++) {
      if (highs[m] > hh) hh = highs[m]
      if (lows[m] < ll) ll = lows[m]
    }
    const rsv = hh === ll ? 50 : ((closes[i] - ll) / (hh - ll)) * 100
    prevK = (2 / 3) * prevK + (1 / 3) * rsv
    prevD = (2 / 3) * prevD + (1 / 3) * prevK
    k.push(round2(prevK))
    d.push(round2(prevD))
    j.push(round2(3 * prevK - 2 * prevD))
  }
  return { k, d, j }
}
