import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { preset } from '../src/api/strategyStudio'
import type { SavedStrategy, StrategySpec } from '../src/api/strategyStudio'

async function setup(page: Page, configured = true) {
  const state = {
    configured,
    blocked: false,
    failAgent: false,
    library: [] as SavedStrategy[],
    executions: [] as { spec: StrategySpec; symbols: { market: string; symbol: string }[] }[],
    factors: [] as Record<string, unknown>[],
    prompts: [] as string[],
  }
  await page.route('http://127.0.0.1:4173/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname.slice(5)
    const body = route.request().method() === 'POST' ? route.request().postDataJSON() : null
    if (path === 'data/symbols')
      return route.fulfill({
        json: [
          {
            market: 'cn',
            symbol: '600519',
            rows: 100,
            startDate: '2024-01-01',
            endDate: '2024-05-31',
          },
        ],
      })
    if (path === 'backtest/strategies' || path === 'data/providers')
      return route.fulfill({ json: [] })
    if (path === 'strategies/capabilities')
      return route.fulfill({
        json: {
          configured: state.configured,
          model: '合成测试模型',
          factors: state.factors,
          execution: '独立回测',
        },
      })
    if (path === 'strategies/library') {
      if (!body) return route.fulfill({ json: state.library })
      const item = { ...body, id: body.id ?? 'a'.repeat(32), version: (body.version ?? 0) + 1 }
      state.library = [item]
      return route.fulfill({ json: item })
    }
    if (path === 'strategies/draft') {
      state.prompts.push(body.prompt)
      if (state.failAgent)
        return route.fulfill({ status: 502, json: { detail: '策略模型服务连接失败' } })
      return route.fulfill({
        json: {
          summary: '合成测试：已整理动量与风险条件。',
          spec: preset(),
          questions: state.blocked ? ['请明确买入阈值'] : [],
          unsupported: state.blocked ? ['组合调仓尚未支持'] : [],
          ready: !state.blocked,
        },
      })
    }
    if (path === 'strategies/validate') {
      if (body.code || !body.entry)
        return route.fulfill({ status: 422, json: { detail: '规则不允许任意代码' } })
      return route.fulfill({ json: body })
    }
    if (path === 'strategies/execute') {
      state.executions.push(body)
      return route.fulfill({
        json: {
          spec: body.spec,
          execution: '合成验证 · T日收盘，下一交易日开盘',
          results: [
            {
              market: 'cn',
              symbol: '600519',
              holding: true,
              dataAsOf: '2024-05-31',
              metrics: { totalReturn: 0.1, maxDrawdown: -0.05, sharpeRatio: 1.2 },
              equityCurve: [
                { date: '2024-05-30', equity: 1 },
                { date: '2024-05-31', equity: 1.1 },
              ],
              lastSignal: { type: 'buy', date: '2024-05-30', price: 100 },
            },
          ],
        },
      })
    }
    if (path === 'strategies/factors') {
      const info = { ...body, rows: body.observations.length }
      state.factors.push(info)
      return route.fulfill({ json: info })
    }
    return route.fulfill({ status: 404, json: { detail: path } })
  })
  await page.goto('/strategies')
  await expect(page.getByRole('heading', { name: '把想法，变成可验证的策略' })).toBeVisible()
  return state
}

test('agent draft can be edited saved reloaded and executed', async ({ page }) => {
  const state = await setup(page)
  await page
    .getByLabel('策略想法', { exact: true })
    .fill('20日涨幅超过5%，波动率低于40%买入，亏损5%止损。')
  await page.getByRole('button', { name: '让 Agent 整理策略' }).click()
  await expect(page.getByText('合成测试：已整理动量与风险条件。')).toBeVisible()
  await page.getByLabel('入场条件1右侧数值', { exact: true }).fill('0.08')
  await page.getByRole('button', { name: '保存策略', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('第 1 版')
  expect(state.library[0]!.spec.entry.conditions[0]!.right.value).toBe(0.08)
  await page.reload()
  await page.getByLabel('加载已保存策略').selectOption('a'.repeat(32))
  await expect(page.getByLabel('入场条件1右侧数值', { exact: true })).toHaveValue('0.08')
  await page.getByLabel('自定义策略执行标的').selectOption(['cn/600519'])
  await page.getByRole('button', { name: '执行回测 / 计算信号' }).click()
  await expect(page.getByRole('cell', { name: '10.00%', exact: true })).toBeVisible()
  await expect(page.getByText('持有 · 2024-05-31')).toBeVisible()
  expect(state.executions[0]!.spec.entry.conditions[0]!.right.value).toBe(0.08)
  expect(state.prompts).toHaveLength(1)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: test.info().outputPath('strategy-studio-desktop.png'),
    fullPage: true,
  })
  await page.getByRole('button', { name: 'JSON规则', exact: true }).click()
  const editor = page.getByLabel('策略JSON规则')
  await editor.fill((await editor.inputValue()).replace('动量与波动率策略', '编辑后的策略'))
  await expect(page.getByRole('cell', { name: '10.00%', exact: true })).toHaveCount(0)
})

test('agent questions and unsupported intent remain blocked after reactive updates', async ({
  page,
}) => {
  const state = await setup(page)
  state.blocked = true
  await page.getByLabel('策略想法', { exact: true }).fill('帮我选股并进行组合调仓')
  await page.getByRole('button', { name: '让 Agent 整理策略' }).click()
  await expect(page.getByText('待补充：请明确买入阈值')).toBeVisible()
  await expect(page.getByText('尚不支持：组合调仓尚未支持')).toBeVisible()
  await expect(page.getByRole('button', { name: '执行回测 / 计算信号' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '保存策略', exact: true })).toBeDisabled()
  expect(state.executions).toHaveLength(0)
})

test('unconfigured model leaves manual strategy editing available', async ({ page }) => {
  await setup(page, false)
  await expect(page.getByText('模型服务待配置', { exact: true })).toBeVisible()
  await page.getByLabel('策略想法', { exact: true }).fill('我的策略想法')
  await expect(page.getByRole('button', { name: '让 Agent 整理策略' })).toBeDisabled()
  await page.getByRole('button', { name: '估值 / 情绪', exact: true }).click()
  await expect(page.getByLabel('入场条件1左侧因子名')).toHaveValue('pe_ttm')
  await page.getByRole('button', { name: '保存策略', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已保存')
})

test('invalid JSON is rejected without replacing current executable rules', async ({ page }) => {
  const state = await setup(page)
  await page.getByRole('button', { name: 'JSON规则', exact: true }).click()
  await page
    .getByLabel('策略JSON规则')
    .fill(JSON.stringify({ ...preset(), code: 'arbitrary-python' }))
  await page.getByRole('button', { name: '校验并应用JSON' }).click()
  await expect(page.getByRole('alert')).toContainText('不允许任意代码')
  await page.getByRole('button', { name: '条件编辑', exact: true }).click()
  await expect(page.getByLabel('策略JSON规则')).toBeVisible()
  expect(state.executions).toHaveLength(0)
  await page.getByRole('button', { name: '均线交叉', exact: true }).click()
  await expect(page.getByLabel('策略JSON规则')).toHaveValue(/自定义双均线/)
})

test('factor imports preserve availability timestamp and source', async ({ page }) => {
  const state = await setup(page)
  await page.getByText('外部因子数据 · 财务 / 情绪 / 宏观 / 事件', { exact: true }).click()
  await page.getByLabel('因子所属标的').selectOption('cn/600519')
  await page.getByLabel('因子名称', { exact: true }).fill('event_score')
  await page.getByLabel('因子数据来源').fill('合成事件披露测试')
  await page.getByLabel('因子发布时间和值').fill('availableAt,value\n2024-01-02T18:00:00+08:00,1')
  await page.getByRole('button', { name: '导入因子序列' }).click()
  await expect(page.getByRole('status')).toContainText('已导入 600519 / event_score')
  expect(state.factors[0]!.observations).toEqual([
    { availableAt: '2024-01-02T18:00:00+08:00', value: 1 },
  ])
})

test('model failure is visible and mobile studio stays within the page', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const state = await setup(page)
  state.failAgent = true
  await page.getByLabel('策略想法', { exact: true }).fill('测试模型故障')
  await page.getByRole('button', { name: '让 Agent 整理策略' }).click()
  await expect(page.getByRole('alert')).toContainText('模型服务连接失败')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({
    path: test.info().outputPath('strategy-studio-mobile.png'),
    fullPage: true,
  })
})
