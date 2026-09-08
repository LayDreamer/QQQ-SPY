# Investment Score V0.1

一个面向 QQQ / SPY 的本地、可解释、可回测投资评分最小系统。它同步日线、VIX 与美国国债收益率到 SQLite，计算固定规则的 Investment Score 和 Signal，并用未来 20/60/120/250 个交易日收益检验高分样本。

> 本项目只提供规则研究工具，不构成投资建议，也不连接券商或执行交易。

## 技术栈

- Python 3.12+
- SQLite（`sqlite3`，WAL 模式）
- pandas / numpy / httpx / python-dotenv / pytest

## 安装

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

默认配置无需 API Key。可在 `.env` 修改：

```env
MARKET_DATA_PROVIDER=nasdaq
MARKET_API_KEY=
MARKET_API_SECRET=
DATABASE_PATH=./data/investment.db
DEFAULT_START_DATE=2010-01-01
HTTP_TIMEOUT=30
```

当前股票 Provider 支持 `nasdaq`（默认）和 `yahoo`；当前运行环境下 Yahoo 可能返回 403。VIX、US10Y 和 US2Y 固定从 FRED 获取。

## 使用

### Windows 一键启动

直接双击项目根目录中的 `run.bat`，或在 PowerShell 中执行：

```powershell
.\run.bat
```

不带参数时，它会自动检查虚拟环境和依赖，并执行完整的 `daily` 流程：同步数据、计算 QQQ/SPY 评分以及生成日报。

也可以用它运行指定命令：

```powershell
.\run.bat init
.\run.bat sync
.\run.bat score --symbol QQQ
.\run.bat backtest
```

### 本地可视化仪表盘

双击 `run_web.bat`，或执行：

```powershell
.\run_web.bat
```

浏览器会自动打开 `http://127.0.0.1:8765/`。页面展示：

- QQQ / SPY 最新 Score、Market State 与 Signal
- Trend / Drawdown / Risk / Macro 分项
- 最近两年评分趋势图和可访问的数据表
- 20D / 60D / 120D / 250D 高分样本回测摘要
- SQLite 行情、宏观及评分记录数量
- “更新数据”按钮：执行与 `run.bat` 相同的同步、重新评分和日报生成流程
- “数据来源”按钮：显示或隐藏五组数据的官方来源、系列代码、本地覆盖区间和记录数

点击“更新数据”后，按钮会显示更新状态并防止重复提交；成功后页面自动载入最新结果。关闭网页服务时在启动窗口按 `Ctrl+C`。

### 手动运行

```powershell
python main.py init
python main.py sync
python main.py score
python main.py backtest
python main.py daily
```

可选参数：

```powershell
python main.py sync --start 2020-01-01
python main.py score --symbol QQQ
python main.py score --date 2026-09-08
python main.py backtest --symbol SPY
```

- `init`：创建数据库、三张核心表和唯一索引。
- `sync`：首次从默认起始日请求；以后从数据库最后日期回退 5 天 UPSERT。
- `score`：重算并保存所有可计算日期；指定非交易日时返回不晚于该日期的最近交易日。
- `backtest`：生成逐日 forward returns、六档阈值汇总，并输出完整可用行情样本的 Buy & Hold CAGR/最大回撤。
- `daily`：只有五组同步全部成功时才继续评分并保存 Markdown 日报。

网络或某个 Provider 失败时，已成功的数据会保留，命令返回非零状态；`daily` 会停止，不会用缺失数据生成假 Score。

## 数据与输出

- SQLite：`data/investment.db`
- 数据表：`market_daily`、`macro_daily`、`investment_score`
- 回测明细：`output/backtest/QQQ_backtest.csv`、`SPY_backtest.csv`
- 回测汇总：`output/backtest/summary.csv`
- 日报：`output/reports/YYYY-MM-DD.md`

数据库写入均以 `(symbol, date)` 或 `(series, date)` UPSERT，重复同步不会产生重复记录。

## 评分规则摘要

总分固定为：Trend 35 + Drawdown 25 + Risk 20 + Macro 20。

- Trend：价格相对 MA20/50/100/200、均线结构、20/60/120 日动量。
- Drawdown：相对 252 交易日高点的回撤；回撤越深，该分项越高。
- Risk：VIX 水平，以及 VIX 高于 25 时 MA5 低于 MA20 的一分修正。
- Macro：US10Y 水平、US10Y/US2Y 的 20/60 日趋势和 10Y-2Y 利差。
- Signal：在总分基础上加入四项确认；长期趋势破坏时禁止 `BUY_3`。

所有滚动指标只使用当日及历史数据。行情交易日为主索引；宏观数据仅向前填充，VIX 最多向前填充一个行情交易日，均不从未来向过去回填。Forward Return 只用于回测评价。

## 测试

```powershell
pytest
```

测试覆盖指标、评分、Signal 降级与长期趋势保护、SQLite 幂等 UPSERT，以及 Forward Return 方向。

## 当前限制

- Nasdaq 公共历史接口当前只返回约最近 10 年，即使 `DEFAULT_START_DATE` 更早；实际数据库从 Provider 能提供的最早日期开始。
- 使用未复权收盘价，回测收益不含股息；本阶段定位是 Score 分层验证，而不是交易级收益核算。
- 公共端点可能限流或调整格式；Provider 已隔离在 `src/market.py` 与 `src/macro.py`。
- M1 不包含 Breadth、估值、宏观扩展、机器学习、Web API 或自动交易。
