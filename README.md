# 量化工作台 (Quant Workbench)

个人量化**监控**工作台:盯自选股、按你绑定的策略发出买入/卖出提示,**不做实盘对接**——看到信号后手动下单。覆盖 **A股 / 港股 / 美股**。

## 功能

| 模块 | 说明 |
| --- | --- |
| 自选股监控 | 左侧列表:实时价(3s 快照轮询)、涨跌幅、持仓状态、最近策略信号(悬停看说明);删除按钮悬停才显示 |
| 行情面板 | 同花顺式:大字现价/涨跌 + 今开/昨收/最高/最低/换手率/成交额/振幅/市盈率/市净率/总市值 |
| 分时图 | 当日分钟线 + 均价线 + 昨收虚线 + 分时量柱,3s 自动更新(A股/港股) |
| K线图 | 日/周/月切换,红涨绿跌 + MA5/10/20/60 + 成交量 + MACD,底部带迷你走势的拖动滑动条,B/S 买卖点标记 |
| 买卖信号提示 | 信号面板:当前持仓状态 + 最近信号(日期/触发价)+ 完整历史;T 日收盘出信号,T+1 手动执行 |
| 策略设置与回测 | 抽屉:切换策略、调参数实时预览信号、保存绑定、一键回测(指标+净值曲线) |
| 行情刷新 | 3s 快照轮询(价格/分时);「刷新K线/信号」按钮拉取最新K线并重算信号 |

## 技术栈

- **后端**: Python 3.13 (conda `quant` 环境) + FastAPI + pandas + Parquet 本地存储
- **前端**: Vue 3 + TypeScript + Element Plus + Tailwind CSS + Pinia + ECharts

## 目录结构

```
quant/
├── start.sh              # 一键启动前后端
├── backend/
│   ├── app/
│   │   ├── api/          # data / backtest / watchlist / monitor 四组路由
│   │   ├── backtest/     # 回测引擎、指标、策略(双均线、RSI)
│   │   ├── data/         # 腾讯(A股/港股)+ yfinance(美股)+ Parquet 存储
│   │   ├── monitor/      # 信号计算服务
│   │   ├── watchlist/    # 自选股 JSON 持久化
│   │   └── schemas/      # Pydantic 模型
│   └── tests/            # pytest(33 个用例)
├── frontend/src/
│   ├── views/WorkbenchView.vue      # 单页工作台
│   ├── components/ThsKLineChart.vue # 同花顺风格K线
│   ├── components/WatchlistPanel.vue# 左侧自选列表
│   ├── components/SignalPanel.vue   # 底部信号面板
│   ├── components/StrategyDrawer.vue# 策略设置/回测抽屉
│   └── utils/indicator.ts           # MA/MACD 计算
└── data/                 # 行情 Parquet + watchlist.json(运行时生成)
```

## 快速开始

```bash
# 一键启动(推荐):后端 8080(conda quant 环境)+ 前端 5173,Ctrl+C 同时停止
./start.sh
```

打开 http://localhost:5173 → 左侧「+ 添加」输入代码(如 600519 / 00700 / AAPL)→ 点击股票看K线与信号 → 「策略设置 / 回测」调整策略。

> **网络说明**:A股/港股走腾讯行情接口直连;美股走 yfinance 需代理(自动读 `QUANT_PROXY` 或 macOS 系统代理)。腾讯接口单次上限约 640 根K线。

## 信号口径

策略在 **T 日收盘**产生信号(图上 B/S 标记在 T 日),你 **T+1 日开盘**手动执行;
回测引擎同样按 T+1 生效计费,保证信号与回测口径一致、无前视偏差。

## 内置策略

| 策略 | name | 参数 |
| --- | --- | --- |
| 双均线交叉 | `sma_cross` | fastWindow(默认5), slowWindow(默认20) |
| RSI 均值回归 | `rsi_reversion` | window(默认14), oversold(默认30), overbought(默认70) |

## 开发

```bash
# 后端测试(conda quant 环境)
cd backend && $(conda info --base)/envs/quant/bin/python -m pytest tests/ -q

# 前端类型检查 + 构建 / lint
cd frontend && npm run build && npx eslint src/
```

## 新增一个策略

1. 在 `backend/app/backtest/strategies/` 新建文件,继承 `Strategy` 基类
2. 实现 `generateSignals()` 返回 0/1 持仓序列
3. 在 `strategies/__init__.py` 注册 —— 监控信号、回测、前端参数表单全部自动生效
