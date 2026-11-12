# 第三方接口统一管理与行情下载

**唯一管理入口：`backend/app/data/third_party.py`。**

该文件顶部维护 `DEFAULT_PROVIDERS` 和 `PROVIDERS`，下方集中所有外部HTTP/SDK调用。Provider文件只做格式转换和行情口径校验。修改配置后重启后端即可生效。

## 修改位置

| 需要修改的信息 | `third_party.py` 内的位置 |
| --- | --- |
| 各市场历史/快照/分时的默认数据源 | `DEFAULT_PROVIDERS`，三类用途独立设置 |
| 停用某个源、支持市场/周期/复权方式 | `PROVIDERS[源名]` 的 `enabled/markets/periods/adjustments` |
| 腾讯地址、超时、返回条数 | `PROVIDERS['tencent']` 的 `urls/timeouts/maxBars` |
| 腾讯字段位置、涨跌幅/金额倍率、编码 | `barFields/quoteFields/quoteScales/encoding/minuteFields` |
| Yahoo SDK入口、周期、返回字段、超时 | `PROVIDERS['yahoo']` 及 `yahooHistory` |
| AKShare函数名、参数名、字段名和底层来源 | `PROVIDERS['akshare']` 的 `methods/params/columns/source` |
| 市场总览快照、行业、指数、估值接口及指数清单 | `MARKET_OVERVIEW` 的 `calls/indices/trendIndices/styleIndices` 和 `marketOverviewRequest` |
| OpenAI兼容策略Agent的地址/模型/密钥环境变量、路径、超时和输出上限 | `AGENT_SETTINGS`、`agentStatus` 和 `strategyAgentRequest` |
| BaoStock主机、端口、超时、登录/查询/退出、字段及复权标志 | `PROVIDERS['baostock']` 及 `runBaostock` |
| 更换代理来源或增加鉴权参数 | 对应的集中调用函数；私密值应从环境变量读取 |

**SDK地址边界：** AKShare、yfinance的底层HTTP地址由其SDK内部管理，配置中标记 `sdkManaged: True`。本文件集中管理SDK调用信息，不能仅修改 `networkHosts` 等说明值就假装替换了SDK内部地址。SDK改接口时，可在本文件换调用函数/参数，升级SDK，或在本文件实现对应HTTP调用；不要修改其他业务模块。

BaoStock使用TCP而非HTTP。主机、端口实际写入独立数据进程的SDK配置；读/连接超时及总请求超时受配置限制。每个请求独立登录、查询、退出，防止多请求相互覆盖全局登录会话。

## 当前能力

| 来源 | 适配市场 | 周期 | 复权 | 成交量 |
| --- | --- | --- | --- | --- |
| 腾讯 | A股、常见A股指数、港股股票 | 日/周/月 | 股票不复权/前复权/后复权；指数不复权 | A股手、港股股 |
| Yahoo / yfinance | 美股股票/ETF | 日/周/月 | 不调整或Yahoo自动调整价 | 股 |
| AKShare（东方财富接口） | 沪深A股、常见沪深指数、港股股票 | 日/周/月 | 股票不复权/前复权/后复权；指数不复权 | A股手、港股股 |
| BaoStock | 沪深A股、常见沪深指数 | 日/周/月 | 股票不复权/前复权/后复权；指数不复权 | 股 |

当前AKShare/BaoStock适配不宣称支持北交所，相关代码会明确拒绝。BaoStock日线股票中明确标为 `tradestatus=0` 的停牌行会排除，并记录排除行数；不会将空价格伪造为0。其他异常数据仍由统一校验拒收。

## 页面使用

打开 **策略中心 → 行情下载**，选择数据源、市场、代码、日期、周期和复权方式，然后下载CSV或JSON。默认选择不复权，便于同日价量核对。CSV每行附带 `meta_` 口径列，JSON包含 `dataInfo` 和 `bars`。

下载不写入活动缓存，不会因为选择其他来源就改变正在监控的策略数据。

## API

`GET /api/data/providers` 返回数据源能力清单，不暴露内部连接配置或凭据。

`POST /api/data/download?format=json`（也可 `format=csv`）：

```json
{
  "source": "akshare",
  "market": "cn",
  "symbol": "600519",
  "startDate": "2026-11-02",
  "endDate": "2026-11-10",
  "period": "day",
  "adjustment": "none"
}
```

将 `source` 改为 `baostock` 可下载对应来源。指数示例为 `symbol: "sh000001"`，使用 `adjustment: "none"`。`000001`仍表示平安银行。返回JSON或带附件文件名的CSV/JSON，可直接保存文件。

`POST /api/data/fetch` 支持相同选择参数，但会写入本地缓存。已有缓存与新来源/口径不同，默认拒绝拼接。如果明确需要切换，先修改 `DEFAULT_PROVIDERS['history']`，再用上述请求加 `"replaceCache": true`，旧文件会备份为 `.parquet.bak` 后重建。后续刷新按统一配置的默认源执行。

`source`省略时使用配置默认源；`adjustment`省略时股票使用该源默认值，指数使用不复权。

## 网络验证与限制

本环境已实际尝试新增来源：AKShare请求东方财富被HTTPS代理以403阻断；BaoStock登录失败，当前环境也未配置该目标的TCP外连权限。因此接口实现和固定响应回归已验证，真实行情内容的验收尚未通过。

- AKShare当前使用的域名包括 `push2his.eastmoney.com`、`33.push2his.eastmoney.com`，指数查询还可能调用 `push2.eastmoney.com` 及其编号子域。应按真实调用补充网络白名单。
- BaoStock目标为 `public-api.baostock.com:10030`，需要TCP外连支持。仅允许网页域名不等于开放TCP连接。
- 现有腾讯/Yahoo网络限制仍见 `live-market-verification.md`。

连接错误返回502，真实空数据返回404，不支持的参数返回422；错误不会作为正常文件下载或写入缓存。

## 自动验证

167项后端测试及24项浏览器回归通过，前端构建、lint与依赖完整性检查通过。覆盖配置修改生效、SDK调用及复权映射、登录/退出清理、超时进程回收、下载文件内容、错误反馈和显式备份切换。

当前只有腾讯适配报价和分时；AKShare、BaoStock和Yahoo适配历史行情。`operations`声明能力，不能把仅有历史下载的适配器配置成实时推送来源。

市场总览另有独立的AKShare快照、行业与估值采集入口，详见 [市场总览说明](market-overview.md)，不会改变原行情监控的默认源。估值SDK的JS运行时使用独立子进程，总请求超时与退出回收在本文件管理。
