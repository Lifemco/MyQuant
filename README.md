# 个人量化工作台 MyQuant

用于 A 股、港股和美股的个人行情观察、策略信号和日线回测。信号用于人工决策，交易由用户手动执行，不接实盘账户。

## 启动

需要 Python 3.12/3.13、Node.js 24（或 Vite 支持的 Node 版本）。Linux/macOS 可直接使用项目虚拟环境；已有 conda `quant` 环境也可继续使用。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-lock.txt
cd frontend
npm ci
cd ..
./start.sh
```

打开 http://localhost:5173 。后端文档为 http://localhost:8080/docs 。设置 `PYTHON_BIN=/path/to/python ./start.sh` 可指定解释器。Ctrl+C 会停止本次启动的前后端进程。

## 功能

- 左侧导航：桌面可折叠，手机保持左侧窄栏；新版K线采用主图优先、MACD/KDJ切换、近期窗口、长按十字线、缩放复位及全屏交互，见 [K线使用说明](docs/kline-interaction.md)。
- 策略工作室：大白话策略Agent（可配置OpenAI兼容服务）、AND/OR条件编辑、外部财务/情绪/事件因子、风控、版本保存和回测/最新信号，见 [策略工作室](docs/strategy-studio.md)。
- 市场总览：六张A股图表覆盖大盘走势与成交额、行业热力、全市场涨跌分布、MA20/MA60市场宽度、规模/价值成长风格和沪深300估值历史分位。每图显示来源、行情日期、抓取时间与覆盖口径，支持后台采集和独立缓存。
- 行情监控：添加自选股（A股6位、港股5位、美股代码可含点和连字符），查看行情快照、分时、日/周/月 K 线、MA/MACD/KDJ 和买卖标记。
- 策略设置：双均线、RSI 均值回归、S1 趋势均线、S2 放量突破。参数编辑期间明确显示“预览”，关闭抽屉恢复已保存策略。
- 策略中心：对最多20只缓存股票执行批量回测；对单只股票的候选参数网格寻优，最多200组，按夏普排序。结果为样本内比较。
- 刷新 K 线/信号：更新日线及已经缓存的周/月线，显示逐票失败原因和数据实际截止日期。快照与分时每3秒轮询，超过50只自选时分批请求。

## 信号及回测口径

- T 日收盘产生信号，**下一根交易日 K 线的开盘价成交**。回测使用现金与股数记账，买入费率包含在可用现金内；每笔买/卖各收一次单边手续费，默认万三。不模拟滑点、最低佣金、印花税、整手数量、停牌和涨跌停的成交限制。
- 单笔盈亏包含买入和卖出手续费、入场日涨跌及卖出前的隔夜涨跌。期末未平仓交易按最后收盘价估值；胜率只统计已平仓交易，交易次数包含未平仓单。
- 夏普为日超额收益均值/样本标准差乘以 `sqrt(252)`，无风险年利率2%；CAGR 单独作为年化收益。不足两个收益样本时波动与夏普返回0，避免 NaN。
- 图表可以显示盘中 K 线；正式买卖点、目标仓位和回测只使用已确认收盘的 K 线。按交易所时区判断：A股15:00、港股16:10、美股纽约16:00之后确认。周线到周五收盘，月线到日历月末收盘之后确认。
- 收盘确认采用**保守时间规则**，尚未集成完整交易所节假日/半日市日历。提前收市日的当天信号、遇假期提前结束的周/月线，可能延后确认；不会据此提前发出正式信号。夏令时按纽约时区自动处理。

## 数据与缓存

- A股/港股使用腾讯前复权行情；客户端遵循 `HTTP_PROXY` / `HTTPS_PROXY` 和系统 CA 配置。腾讯每次最多约640根 K 线。
- 美股使用 yfinance 的调整后日线，**没有实时快照或分时支持**。界面会标记缓存收盘价及日期，需手动刷新。国内网络可按需配置 Yahoo 代理。
- Parquet 按日期增量合并，JSON 自选清单和行情采用写锁与原子替换，避免并发丢失更新或读到半写文件。
- 若重叠的历史价格发生复权修订，旧文件备份为 `.parquet.bak`，使用本次数据源返回的完整窗口重建，**不拼接两套复权基准**。历史可能缩短到数据源返回范围，界面显示重建提示。备份保留最近一次重建前版本，可人工恢复；无重叠历史时也采用同一保护策略。
- 仓库内已有行情仅作为样例，不能视为当前行情；实际截止日期在页面可见。新增运行文件已加入忽略规则；仓库原有的样例行情和自选文件仍保留。

## 检查

```bash
# 后端
.venv/bin/python -m pytest backend/tests/ -q
# 或 cd backend 后执行 python -m pytest tests/ -q

# 前端
cd frontend
npm run build
npx eslint src/ tests/ playwright.config.ts
npx playwright install chromium
npm run test:e2e
```

若使用系统 Chromium：`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e`。浏览器回归通过模拟行情接口验证，不依赖真实行情服务。CI 执行后端测试、前端构建、lint 和浏览器回归。

## 结构与扩展

后端 `backend/app/` 分为 `api`、`backtest`、`data`、`market`、`monitor`、`schemas`、`watchlist`；前端 `frontend/src/` 使用 Vue 3 + TypeScript + Element Plus + Pinia + ECharts。

新增 `backend/app/strategies/` 提供可编辑规则和时点因子。Vue与Python各有独立Dockerfile，生产通过Nginx `/api`代理连接；完整K8s部署清单、环境配置及单后端持久化边界见 [云上部署说明](docs/cloud-deployment.md)。此清单尚未连接你的集群执行部署。

添加策略：继承 `Strategy`，实现按行情日期索引的0/1目标持仓序列，并在 `strategies/__init__.py` 注册及声明参数范围。服务端统一校验参数类型、边界和跨参数关系，再用于绑定、监控、回测及寻优。

本地启动脚本仅绑定本机地址，默认CORS允许本地开发页面；生产容器监听8080，通过Nginx同源代理及K8s ClusterIP连接。当前没有账户认证，对外访问需由部署方的鉴权网关保护。

## 行情口径校验

数据带有来源、复权、成交量单位、币种和采集时点等信息。不同来源/复权/单位的表不能直接拼接；跨源核对仅比较同标的共同交易日的已确认、不复权价量，先统一成交量单位。旧缓存会标记口径未知，刷新时备份重建。

输入 `000001` 代表平安银行，`sh000001` 代表上证指数，二者独立存储。页面显示K线来源、价格复权及成交量单位。规则、误差阈值和现有接入范围见 [行情口径说明](docs/market-data-conventions.md)。

## 第三方接口与文件下载

第三方地址、超时、SDK入口、参数及字段映射集中在 **`backend/app/data/third_party.py`**；历史、快照、分时可分别配置默认源，修改后重启后端。

已接入AKShare和BaoStock历史下载。在 **策略中心 → 行情下载** 选择来源、日期与复权方式即可下载CSV/JSON。API为 `GET /api/data/providers` 和 `POST /api/data/download`，带有来源和口径信息。

安装新增SDK请重新执行 `pip install -r backend/requirements-lock.txt`。能力范围、缓存切换、配置修改及网络限制见 [第三方接口说明](docs/third-party-interfaces.md)。

## 市场总览

打开导航中的 **市场总览**（`/market`），点击 **刷新市场数据**。六图所需第三方配置与调用仍统一在 `backend/app/data/third_party.py` 的 `MARKET_OVERVIEW` 区域。数据缺失时展示空态，失败时保留并标记旧缓存，不使用自选股替代全市场。

MA20/MA60图需先刷新证券名单，再点击 **构建 / 更新全市场宽度**。首次会逐只下载沪深A股历史，耗时较长；采集在后台执行，显示进度、失败数量与实际分母，同一目标日可复用成功缓存。当前使用最新名单回溯，存在幸存者偏差，不作为历史时点完整股票池。详细口径及验证见 [市场总览说明](docs/market-overview.md)。
