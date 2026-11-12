import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

async function mockWorkbench(page: Page, count = 2, fullHistory = false) {
  const codes =
    count === 2
      ? ['600519', '000001']
      : ['600519', ...Array.from({ length: count - 1 }, (_, i) => String(i).padStart(6, '0'))]
  let items = codes.map((symbol, index) => ({
    market: 'cn',
    symbol,
    name: index === 0 ? '测试甲' : '测试乙',
    strategy: 'sma_cross',
    params: { fastWindow: 5, slowWindow: 20 },
    holding: false,
    lastSignal: null,
    close: index === 0 ? 100 : 200,
    changePct: 0,
    dataAsOf: '2026-09-29',
    signalAsOf: '2026-09-29',
  }))
  const state = {
    legacyMetadata: false,
    delayA: false,
    delayStrategies: false,
    failChart: false,
    failDownload: false,
    downloads: [] as { source: string; symbol: string; startDate: string; adjustment: string }[],
    quoteRequests: [] as number[],
    chartParams: [] as number[],
    batchSizes: [] as number[],
    optimizeGrids: [] as Record<string, number[]>[],
  }
  await page.route('http://127.0.0.1:4173/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.slice('/api/'.length)
    if (path === 'strategies/capabilities')
      return route.fulfill({
        json: { configured: false, model: null, factors: [], execution: '独立回测' },
      })
    if (path === 'strategies/library') return route.fulfill({ json: [] })
    if (path === 'monitor/overview') return route.fulfill({ json: items })
    if (path === 'monitor/quotes') {
      state.quoteRequests.push(route.request().postDataJSON().items.length)
      return route.fulfill({ json: [] })
    }
    if (path.startsWith('watchlist/') && route.request().method() === 'DELETE') {
      items = items.filter((item) => !path.endsWith(item.symbol))
      return route.fulfill({ status: 204 })
    }
    if (path === 'backtest/strategies') {
      if (state.delayStrategies) await new Promise((resolve) => setTimeout(resolve, 400))
      return route.fulfill({
        json: [
          {
            name: 'sma_cross',
            label: '双均线交叉',
            paramsSchema: {
              fastWindow: { type: 'int', default: 5, min: 2, max: 60, desc: '快线周期' },
              slowWindow: { type: 'int', default: 20, min: 5, max: 250, desc: '慢线周期' },
            },
          },
        ],
      })
    }
    if (path === 'data/providers')
      return route.fulfill({
        json: [
          {
            id: 'tencent',
            label: '腾讯',
            enabled: true,
            markets: ['cn', 'hk'],
            periods: ['day', 'week', 'month'],
            adjustments: ['none', 'qfq', 'hfq'],
          },
          {
            id: 'yahoo',
            label: 'Yahoo / yfinance',
            enabled: true,
            markets: ['us'],
            periods: ['day', 'week', 'month'],
            adjustments: ['none', 'yahoo_auto_adjust'],
          },
          {
            id: 'akshare',
            label: 'AKShare（东方财富）',
            enabled: true,
            markets: ['cn', 'hk'],
            periods: ['day', 'week', 'month'],
            adjustments: ['none', 'qfq', 'hfq'],
          },
          {
            id: 'baostock',
            label: 'BaoStock',
            enabled: true,
            markets: ['cn'],
            periods: ['day', 'week', 'month'],
            adjustments: ['none', 'qfq', 'hfq'],
          },
        ],
      })
    if (path === 'data/download') {
      const request = route.request().postDataJSON()
      state.downloads.push(request)
      if (state.failDownload)
        return route.fulfill({ status: 502, json: { detail: '数据源连接失败' } })
      return route.fulfill({
        contentType: 'text/csv',
        headers: { 'Content-Disposition': "attachment; filename*=UTF-8''baostock_600519.csv" },
        body: 'date,close,meta_source\n2024-01-02,100,baostock\n',
      })
    }
    if (path === 'data/symbols')
      return route.fulfill({
        json: items.map((item) => ({
          market: item.market,
          symbol: item.symbol,
          rows: 100,
          startDate: '2026-01-01',
          endDate: item.dataAsOf,
        })),
      })
    const metrics = {
      totalReturn: 0.1,
      annualReturn: 0.2,
      annualVolatility: 0.1,
      sharpeRatio: 1.5,
      maxDrawdown: -0.05,
      calmarRatio: 4,
      totalTrades: 2,
      winRate: 0.5,
    }
    if (path === 'backtest/batch') {
      const req = route.request().postDataJSON()
      state.batchSizes.push(req.symbols.length)
      return route.fulfill({
        json: req.symbols.map((item: { market: string; symbol: string }) => ({ ...item, metrics })),
      })
    }
    if (path === 'backtest/optimize') {
      const req = route.request().postDataJSON()
      state.optimizeGrids.push(req.grid)
      return route.fulfill({ json: [{ params: { fastWindow: 3, slowWindow: 20 }, metrics }] })
    }
    if (path === 'monitor/chart') {
      const req = route.request().postDataJSON()
      state.chartParams.push(req.params.fastWindow)
      if (state.delayA && req.symbol === '600519')
        await new Promise((resolve) => setTimeout(resolve, 500))
      if (state.failChart) return route.fulfill({ status: 502, json: { detail: '上游不可用' } })
      const close = req.symbol === '600519' ? 100 : 200
      const marker = { date: '2026-09-29', type: 'buy', price: close + req.params.fastWindow }
      return route.fulfill({
        json: {
          dataInfo: state.legacyMetadata
            ? null
            : {
                source: fullHistory ? '合成验证数据' : 'tencent',
                market: 'cn',
                symbol: req.symbol,
                period: req.period,
                instrumentId: `cn:${req.symbol === '600519' ? 'sh600519' : 'sz000001'}`,
                instrumentType: 'stock',
                adjustment: 'qfq',
                volumeUnit: 'lot100',
                currency: 'CNY',
                priceUnit: 'currency',
                timezone: 'Asia/Shanghai',
                fetchedAt: '2026-09-30T10:00:00+08:00',
                observedAt: '2026-09-30T10:00:00+08:00',
                confirmedThrough: '2026-09-29',
              },
          bars: fullHistory
            ? Array.from({ length: 180 }, (_, i) => {
                const value =
                  i === 179 ? close : close * (0.65 + (0.35 * i) / 179 + Math.sin(i * 0.29) * 0.025)
                const open = value * (1 + Math.sin(i * 0.71) * 0.015)
                return {
                  date: new Date(Date.UTC(2026, 8, 29) - (179 - i) * 86400000)
                    .toISOString()
                    .slice(0, 10),
                  open,
                  close: value,
                  high: Math.max(open, value) * 1.012,
                  low: Math.min(open, value) * 0.988,
                  volume: (1.3 + Math.sin(i * 0.18)) * 1e6,
                }
              })
            : [
                {
                  date: marker.date,
                  open: close,
                  high: close + 1,
                  low: close - 1,
                  close,
                  volume: 1000,
                },
              ],
          markers: [marker],
          lastSignal: marker,
          holding: true,
          signalAsOf: marker.date,
        },
      })
    }
    return route.fulfill({ status: 404, json: { detail: path } })
  })
  await page.goto('/')
  await expect(page.getByRole('img', { name: 'K线图，最新收盘价 100', exact: true })).toBeVisible()
  return state
}

test('slow old stock response cannot replace the selected chart', async ({ page }) => {
  const state = await mockWorkbench(page)
  state.delayA = true
  await page.getByRole('button', { name: '周线', exact: true }).click()
  await page.getByText('测试乙', { exact: true }).first().click()
  await expect(page.getByRole('img', { name: 'K线图，最新收盘价 200', exact: true })).toBeVisible()
  await page.waitForTimeout(650)
  await expect(page.getByRole('img', { name: 'K线图，最新收盘价 200', exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: 'K线图，最新收盘价 100', exact: true })).toHaveCount(0)
})

test('K-line terminal switches indicators zooms inspects and expands', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await mockWorkbench(page, 2, true)
  await expect(page.getByTestId('candle-count')).toContainText('70 / 180')
  await page.getByRole('button', { name: '放大K线', exact: true }).click()
  await expect(page.getByTestId('candle-count')).not.toContainText('70 / 180')
  await page.getByRole('button', { name: '复位到最近行情' }).click()
  await expect(page.getByTestId('candle-count')).toContainText('70 / 180')
  await page.getByRole('button', { name: 'KDJ', exact: true }).click()
  await expect(page.getByRole('button', { name: 'KDJ', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: '仅成交量', exact: true }).click()
  await page.getByRole('button', { name: 'MACD', exact: true }).click()
  const canvas = page.getByRole('img', { name: 'K线图，最新收盘价 100', exact: true })
  await canvas.focus()
  await canvas.press('ArrowLeft')
  await expect(page.locator('.candle-readout')).toContainText('2026-09-28')
  await page.getByRole('button', { name: '展开图表', exact: true }).click()
  await expect(page.getByTestId('kline-terminal')).toHaveClass(/fullscreen/)
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('kline-terminal')).not.toHaveClass(/fullscreen/)
  await page.getByRole('button', { name: '复位到最近行情' }).click()
  const nav = await page.getByLabel('工作台侧栏').boundingBox()
  expect(nav?.x).toBe(0)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: test.info().outputPath('kline-desktop.png'), fullPage: true })
  expect(errors).toEqual([])
})

test('mobile chart supports long press and sidebar stays at the left', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockWorkbench(page, 2, true)
  const chart = page.getByRole('img', { name: 'K线图，最新收盘价 100', exact: true })
  await expect(page.locator('.el-loading-mask')).toHaveCount(0)
  await chart.scrollIntoViewIfNeeded()
  const box = (await chart.boundingBox())!
  const session = await context.newCDPSession(page)
  await session.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 2 })
  await session.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: box.x + box.width * 0.5, y: box.y + box.height * 0.3 }],
  })
  await expect(page.getByRole('button', { name: '十字线模式' })).toHaveAttribute(
    'aria-pressed',
    'true',
    { timeout: 2000 },
  )
  await session.send('Input.dispatchTouchEvent', {
    type: 'touchMove',
    touchPoints: [{ x: box.x + box.width * 0.6, y: box.y + box.height * 0.3 }],
  })
  await expect(page.locator('.candle-readout')).not.toContainText('2026-09-29')
  await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await expect(page.getByRole('button', { name: '十字线模式' })).toHaveAttribute(
    'aria-pressed',
    'false',
  )
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  const nav = (await page.getByLabel('工作台侧栏').boundingBox())!
  expect(nav.x).toBe(0)
  expect(nav.width).toBe(60)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: test.info().outputPath('kline-mobile.png'), fullPage: true })
})

test('preview updates confirmed panel and closing restores saved parameters', async ({ page }) => {
  const state = await mockWorkbench(page)
  await page.getByRole('button', { name: '策略设置 / 回测' }).click()
  const inputs = page.getByRole('spinbutton')
  await inputs.first().fill('8')
  await inputs.first().press('Tab')
  await expect(page.getByText('策略预览（未保存）')).toBeVisible()
  await expect(page.getByText('@ ¥108', { exact: true })).toBeVisible()
  await page.locator('.el-drawer__close-btn').click()
  await expect(page.getByText('策略预览（未保存）')).toHaveCount(0)
  await expect(page.getByText('@ ¥105', { exact: true })).toBeVisible()
  expect(state.chartParams.at(-1)).toBe(5)
})

test('chart request failure clears old stock data', async ({ page }) => {
  const state = await mockWorkbench(page)
  state.failChart = true
  await page.getByText('测试乙', { exact: true }).first().click()
  await expect(page.getByText('上游不可用', { exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: /K线图/ })).toHaveCount(0)
})

test('deleting selected stock selects the remaining stock', async ({ page }) => {
  await mockWorkbench(page)
  const row = page.locator('aside .group').filter({ hasText: '测试甲' })
  await row.hover()
  await row.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByRole('img', { name: 'K线图，最新收盘价 200', exact: true })).toBeVisible()
})

test('strategy center loads as a real route', async ({ page }) => {
  await mockWorkbench(page)
  await page.getByRole('menuitem', { name: '策略中心' }).click()
  await expect(page.getByRole('heading', { name: '策略中心' })).toBeVisible()
  await expect(page.getByRole('button', { name: '批量回测', exact: true })).toBeVisible()
})

test('quotes are split into batches of at most fifty', async ({ page }) => {
  const state = await mockWorkbench(page, 51)
  await expect.poll(() => state.quoteRequests.slice(0, 2)).toEqual([50, 1])
})

test('strategy center submits batch and optimization requests', async ({ page }) => {
  const state = await mockWorkbench(page)
  await page.getByRole('menuitem', { name: '策略中心' }).click()
  await page.locator('.el-select').first().click()
  await page
    .locator('.el-select-dropdown')
    .getByRole('option', { name: /CN 600519/ })
    .click()
  await page.getByRole('heading', { name: '策略中心' }).click()
  await page.getByRole('button', { name: '批量回测', exact: true }).click()
  await expect.poll(() => state.batchSizes).toEqual([1])
  await expect(page.getByRole('cell', { name: '10.00%', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '快线周期候选值' }).fill('3,5')
  await page.getByRole('button', { name: '参数寻优（最多200组）', exact: true }).click()
  await expect.poll(() => state.optimizeGrids).toEqual([{ fastWindow: [3, 5], slowWindow: [20] }])
  await expect(page.getByRole('cell', { name: /fastWindow=3/ })).toBeVisible()
})

test('closing while strategy metadata loads cannot start a hidden preview', async ({ page }) => {
  const state = await mockWorkbench(page)
  state.delayStrategies = true
  await page.getByRole('button', { name: '策略设置 / 回测' }).click()
  await page.locator('.el-drawer__close-btn').click()
  await page.waitForTimeout(550)
  await expect(page.getByText('策略预览（未保存）')).toHaveCount(0)
  await expect(page.getByText('@ ¥105', { exact: true })).toBeVisible()
})

test('K-line source adjustment and native units are shown without guessing legacy data', async ({
  page,
}) => {
  const state = await mockWorkbench(page)
  await expect(page.getByTestId('data-convention')).toHaveText('K线：腾讯 · 前复权 · 成交量手')
  state.legacyMetadata = true
  await page.getByRole('button', { name: '周线', exact: true }).click()
  await expect(page.getByTestId('data-convention')).toHaveText(
    'K线来源、复权与单位未确认，请刷新后核对',
  )
})

test('download form selects BaoStock and saves a file with requested dates', async ({ page }) => {
  const state = await mockWorkbench(page)
  await page.getByRole('menuitem', { name: '策略中心' }).click()
  const source = page.getByRole('combobox', { name: '下载数据源', exact: true })
  await expect(source).toBeEnabled()
  await source.locator('xpath=ancestor::div[contains(@class, "el-select__wrapper")]').click()
  await page.getByRole('option', { name: 'BaoStock', exact: true }).click()
  await page.getByLabel('下载股票代码').fill('600519')
  await page.getByLabel('下载开始日期').fill('2024-01-01')
  await page.getByLabel('下载结束日期').fill('2024-01-03')
  const filePromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载行情文件', exact: true }).click()
  const file = await filePromise
  expect(file.suggestedFilename()).toBe('baostock_600519.csv')
  expect(state.downloads[0]).toMatchObject({
    source: 'baostock',
    market: 'cn',
    symbol: '600519',
    startDate: '2024-01-01',
    endDate: '2024-01-03',
    adjustment: 'none',
  })
})

test('download failures show upstream error instead of saving a file', async ({ page }) => {
  const state = await mockWorkbench(page)
  state.failDownload = true
  await page.getByRole('menuitem', { name: '策略中心' }).click()
  await page.getByLabel('下载股票代码').fill('600519')
  await page.getByRole('button', { name: '下载行情文件', exact: true }).click()
  await expect(page.getByText('数据源连接失败', { exact: true })).toBeVisible()
})
