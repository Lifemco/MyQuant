import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import type { MarketOverview, MarketSection, SectionKey } from '../src/api/market'

function fixture(): MarketOverview {
  const date = '2026-11-11'
  function section<T>(data: T): MarketSection<T> {
    return {
      data,
      status: 'ok',
      source: '验证样本 / 非真实行情',
      asOf: date,
      fetchedAt: '2026-11-11T16:00:00+08:00',
      notes: '仅用于自动化验证的合成数据。',
    }
  }
  const points = [
    { date: '2026-11-10', close: 3000, amount: 1e12 },
    { date, close: 3100, amount: 1.2e12 },
  ]
  return {
    job: { running: false },
    sections: {
      trend: section([
        { code: '000001', name: '上证指数', points },
        {
          code: '000300',
          name: '沪深300',
          points: points.map((p) => ({ ...p, close: p.close + 1000 })),
        },
      ]),
      industry: {
        ...section([
          { symbol: 'BK1', name: '行业甲', change: 1.2, size: 1e12 },
          { symbol: 'BK2', name: '行业乙', change: -2, size: 5e11 },
        ]),
        status: 'partial',
        asOf: null,
      },
      distribution: section({
        bins: [
          '<-10',
          '[-10,-7)',
          '[-7,-5)',
          '[-5,-3)',
          '[-3,-1)',
          '[-1,1)',
          '[1,3)',
          '[3,5)',
          '[5,7)',
          '[7,10)',
          '≥10',
        ].map((label, i) => ({ label, count: [0, 0, 0, 5, 5, 20, 10, 10, 5, 0, 5][i]! })),
        total: 70,
        valid: 60,
        excluded: 10,
        up: 30,
        flat: 20,
        down: 10,
      }),
      breadth: {
        ...section({
          total: 5000,
          collected: 4500,
          points: [{ date, ma20: 55, ma60: 40, eligible20: 4400, eligible60: 4300 }],
        }),
        status: 'partial',
      },
      style: section({
        baseDate: '2026-11-10',
        dates: ['2026-11-10', date],
        series: ['沪深300', '中证500', '中证1000', '沪深300成长', '沪深300价值'].map((name, i) => ({
          name,
          values: [100, 101 + i],
        })),
      }),
      valuation: section({
        name: '沪深300',
        metric: 'PE-TTM',
        points: [{ date, pe: 12.3, percentile: 40, samples: 1200 }],
      }),
    },
  }
}

async function mock(page: Page, payload = fixture()) {
  const state = {
    payload,
    failGet: false,
    failBreadth: false,
    refreshing: false,
    posts: [] as string[],
    reads: 0,
  }
  await page.route('http://127.0.0.1:4173/api/market/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === 'GET') {
      state.reads++
      if (state.failGet) return route.fulfill({ status: 502, json: { detail: '服务暂不可用' } })
      if (state.refreshing) {
        state.refreshing = false
        state.payload.job = { running: false, done: 5, total: 5 }
      }
      return route.fulfill({ json: state.payload })
    }
    state.posts.push(path)
    if (state.failBreadth && path.endsWith('breadth'))
      return route.fulfill({
        status: 422,
        json: { detail: '请先刷新市场数据，获取全市场证券名单' },
      })
    state.refreshing = true
    state.payload.job = {
      running: true,
      kind: path.endsWith('breadth') ? 'breadth' : 'refresh',
      done: 1,
      total: 5,
    }
    return route.fulfill({ json: state.payload })
  })
  return state
}

test('six market charts render with provenance, coverage and index selection', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await mock(page)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/market')
  await expect(page.getByRole('heading', { name: '市场总览', exact: true })).toBeVisible()
  await expect(page.locator('.market-chart canvas')).toHaveCount(6)
  for (const title of [
    '大盘走势与成交额',
    '行业涨跌热力图',
    '全市场涨跌分布',
    '站上 MA20 / MA60 占比',
    '规模与价值成长风格',
    '市场估值历史分位',
  ]) {
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  }
  await expect(page.getByTestId('market-distribution')).toContainText('有效 60 / 70')
  await expect(page.getByTestId('market-breadth')).toContainText('4400 只')
  await expect(page.getByTestId('market-breadth')).toContainText('4300 只')
  await expect(page.getByTestId('market-industry')).toContainText('行情日期 源未确认')
  await page.getByRole('combobox', { name: '大盘指数' }).selectOption('000300')
  await expect(page.getByTestId('market-trend')).toContainText('4,100 点')
  await expect(page.getByTestId('market-valuation')).toContainText('窗口 1200 个样本')
  expect(errors).toEqual([])
  await page.screenshot({
    path: test.info().outputPath('market-overview-desktop.png'),
    fullPage: true,
  })
  await page
    .getByTestId('market-industry')
    .screenshot({ path: test.info().outputPath('market-industry.png') })
})

test('refresh runs once and polls until the task finishes', async ({ page }) => {
  const state = await mock(page)
  await page.goto('/market')
  const button = page.getByRole('button', { name: '刷新市场数据', exact: true })
  await expect(button).toBeEnabled()
  await button.click()
  await expect(page.getByRole('status')).toContainText('正在刷新市场数据')
  await expect(button).toBeDisabled()
  await expect(button).toBeEnabled({ timeout: 8000 })
  expect(state.posts).toEqual(['/api/market/refresh'])
  expect(state.reads).toBeGreaterThan(1)
})

test('missing data is empty and breadth prerequisite failure is visible', async ({ page }) => {
  const data = fixture()
  for (const key of Object.keys(data.sections) as SectionKey[]) {
    data.sections[key].data = null
    data.sections[key].status = 'unavailable'
  }
  const state = await mock(page, data)
  state.failBreadth = true
  await page.goto('/market')
  await expect(page.getByText('尚无可展示的数据', { exact: true })).toHaveCount(6)
  await expect(page.locator('.market-chart canvas')).toHaveCount(0)
  await page.getByRole('button', { name: '构建 / 更新全市场宽度' }).click()
  await expect(page.getByRole('alert')).toContainText('请先刷新市场数据')
  await expect(page.getByRole('button', { name: '构建 / 更新全市场宽度' })).toBeEnabled()
})

test('stale cache survives a read failure and retry recovers', async ({ page }) => {
  const data = fixture()
  data.sections.trend.status = 'stale'
  data.sections.trend.error = '本次采集失败，保留上次成功数据。'
  const state = await mock(page, data)
  await page.goto('/market')
  await expect(page.getByTestId('market-trend')).toContainText('缓存数据 / 待更新')
  state.failGet = true
  await page.getByRole('button', { name: '重读缓存' }).click()
  await expect(page.getByRole('alert')).toContainText('服务暂不可用')
  await expect(page.locator('.market-chart canvas')).toHaveCount(6)
  state.failGet = false
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('market page fits mobile', async ({ page }) => {
  await mock(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/market')
  await expect(page.locator('.market-chart canvas')).toHaveCount(6)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({
    path: test.info().outputPath('market-overview-mobile.png'),
    fullPage: true,
  })
})
