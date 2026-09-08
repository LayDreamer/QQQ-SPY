"""Local browser dashboard for Investment Score V0.1."""

from __future__ import annotations

import argparse
import html
import logging
import threading
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

from config import BASE_DIR, settings
from database import connect, get_score_data
from main import calculate_symbol_scores, sync_data
from src.backtest import add_forward_returns, summarize_thresholds
from src.report import generate_daily_report


LOG = logging.getLogger("investment-dashboard")
UPDATE_LOCK = threading.Lock()

STYLE = """
<style>
:root {
  color-scheme: light dark;
  --primary: #1e40af; --primary-2: #3b82f6; --accent: #b45309;
  --bg: #f4f7fb; --surface: #ffffff; --surface-2: #edf2fa;
  --text: #172554; --muted: #52637a; --border: #cbdaf0;
  --good: #047857; --warn: #a16207; --bad: #b91c1c;
  --shadow: 0 8px 30px rgba(30, 64, 175, .08);
  --radius: 16px; --focus: #1d4ed8;
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body { margin: 0; color: var(--text); background: var(--bg); font: 16px/1.5 "Segoe UI", "Microsoft YaHei", sans-serif; }
a { color: inherit; }
.skip { position: fixed; left: 12px; top: -80px; z-index: 100; padding: 10px 14px; background: var(--primary); color: white; border-radius: 8px; }
.skip:focus { top: 12px; }
.shell { width: min(1240px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 48px; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.brand { display: flex; align-items: center; gap: 12px; }
.brand-mark { display: grid; place-items: center; width: 44px; height: 44px; color: white; background: var(--primary); border-radius: 12px; box-shadow: var(--shadow); }
.brand-mark svg { width: 24px; height: 24px; }
h1, h2, h3, p { margin-top: 0; }
h1 { margin-bottom: 2px; font: 700 clamp(20px, 3vw, 28px)/1.2 Consolas, monospace; letter-spacing: -.04em; }
h2 { margin-bottom: 16px; font-size: 18px; }
h3 { margin-bottom: 4px; font-size: 15px; }
.eyebrow, .meta, .muted { color: var(--muted); }
.eyebrow { margin-bottom: 4px; font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.meta { margin: 0; font-size: 13px; }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.button, .segmented a { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; padding: 9px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); color: var(--text); font-weight: 650; text-decoration: none; cursor: pointer; transition: background-color .2s ease, border-color .2s ease, color .2s ease, box-shadow .2s ease; touch-action: manipulation; }
.button:hover, .segmented a:hover { border-color: var(--primary-2); background: var(--surface-2); }
.button:focus-visible, .segmented a:focus-visible, summary:focus-visible, .score-card:focus-visible { outline: 3px solid color-mix(in srgb, var(--focus) 45%, transparent); outline-offset: 2px; }
.button.primary { min-width: 108px; border-color: var(--primary); background: var(--primary); color: white; }
.button.primary:hover { border-color: var(--primary-2); background: var(--primary-2); }
.button[disabled] { cursor: wait; opacity: .72; }
.button.updating::before { content: ""; width: 14px; height: 14px; margin-right: 8px; border: 2px solid rgba(255,255,255,.45); border-top-color: white; border-radius: 50%; animation: spin .8s linear infinite; }
.actions form { display: inline-flex; margin: 0; }
.segmented { display: inline-flex; gap: 4px; padding: 4px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); }
.segmented a { min-width: 70px; min-height: 36px; padding: 6px 12px; border-color: transparent; background: transparent; }
.segmented a[aria-current="page"] { background: var(--primary); color: white; box-shadow: 0 2px 8px rgba(30,64,175,.22); }
.grid { display: grid; gap: 16px; }
.hero-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 16px; }
.main-grid { grid-template-columns: minmax(0, 1.6fr) minmax(280px, .8fr); align-items: start; }
.card { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); box-shadow: var(--shadow); }
.card-pad { padding: 20px; }
.score-card { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 18px; padding: 20px; text-decoration: none; cursor: pointer; transition: border-color .2s ease, box-shadow .2s ease, background-color .2s ease; }
.score-card:hover { border-color: var(--primary-2); box-shadow: 0 12px 34px rgba(30,64,175,.14); }
.score-card.selected { border-color: var(--primary-2); background: linear-gradient(135deg, color-mix(in srgb, var(--primary-2) 8%, var(--surface)), var(--surface)); }
.gauge { --score: 0; --gauge-color: var(--primary-2); position: relative; display: grid; place-items: center; width: 92px; height: 92px; border-radius: 50%; background: conic-gradient(var(--gauge-color) calc(var(--score) * 1%), var(--surface-2) 0); }
.gauge::after { content: ""; position: absolute; inset: 9px; border-radius: inherit; background: var(--surface); }
.gauge-value { position: relative; z-index: 1; font: 700 27px/1 Consolas, monospace; }
.gauge-value small { display: block; margin-top: 5px; color: var(--muted); font: 600 10px/1 "Segoe UI", sans-serif; letter-spacing: .08em; }
.symbol { margin: 0 0 2px; font: 700 25px/1 Consolas, monospace; }
.price { margin: 8px 0 0; font: 650 18px/1 Consolas, monospace; font-variant-numeric: tabular-nums; }
.state { display: inline-flex; margin-top: 7px; padding: 4px 8px; border-radius: 999px; background: var(--surface-2); color: var(--muted); font-size: 12px; font-weight: 700; }
.signal { text-align: right; }
.signal strong { display: block; font: 700 19px/1.2 Consolas, monospace; }
.signal span { color: var(--muted); font-size: 12px; }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.section-head h2 { margin-bottom: 2px; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 18px; height: 3px; border-radius: 3px; background: var(--primary-2); }
.legend .spy { background: var(--accent); background-image: repeating-linear-gradient(90deg, var(--accent) 0 5px, transparent 5px 8px); }
.chart-wrap { overflow: hidden; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.chart-wrap svg { display: block; width: 100%; height: auto; min-height: 250px; }
.metric-list { display: grid; gap: 14px; }
.metric-row { display: grid; grid-template-columns: 105px 1fr 52px; align-items: center; gap: 10px; }
.metric-row label { color: var(--muted); font-size: 13px; }
.metric-row strong { text-align: right; font: 650 13px/1 Consolas, monospace; }
.track { height: 8px; overflow: hidden; border-radius: 999px; background: var(--surface-2); }
.track span { display: block; height: 100%; border-radius: inherit; background: var(--primary-2); }
.facts { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 18px; }
.fact { padding: 13px; border-radius: 12px; background: var(--surface-2); }
.fact span { display: block; color: var(--muted); font-size: 12px; }
.fact strong { display: block; margin-top: 3px; font: 700 16px/1.2 Consolas, monospace; font-variant-numeric: tabular-nums; }
.table-card { margin-top: 16px; }
.table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { background: var(--surface-2); color: var(--muted); font-size: 11px; letter-spacing: .04em; text-transform: uppercase; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: color-mix(in srgb, var(--primary-2) 6%, transparent); }
.empty { padding: 40px 20px; text-align: center; color: var(--muted); }
details { margin-top: 14px; }
summary { min-height: 44px; padding: 11px 0; color: var(--primary); font-weight: 700; cursor: pointer; }
.notice { display: flex; gap: 10px; margin-bottom: 16px; padding: 12px 14px; border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border)); border-radius: 12px; background: color-mix(in srgb, var(--accent) 8%, var(--surface)); color: var(--muted); font-size: 13px; }
.notice strong { color: var(--text); }
.notice.success { border-color: color-mix(in srgb, var(--good) 40%, var(--border)); background: color-mix(in srgb, var(--good) 9%, var(--surface)); }
.notice.error { border-color: color-mix(in srgb, var(--bad) 45%, var(--border)); background: color-mix(in srgb, var(--bad) 8%, var(--surface)); }
.source-panel { margin-bottom: 16px; }
.source-panel[hidden] { display: none; }
.source-panel .section-head { margin-bottom: 12px; }
.source-panel a { color: var(--primary); font-weight: 700; text-underline-offset: 3px; }
.source-note { margin: 12px 0 0; color: var(--muted); font-size: 12px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
footer { margin-top: 24px; color: var(--muted); font-size: 12px; text-align: center; }
@media (max-width: 820px) { .topbar { align-items: flex-start; flex-direction: column; } .actions { justify-content: flex-start; } .main-grid { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .shell { width: min(100% - 20px, 1240px); padding-top: 14px; } .hero-grid { grid-template-columns: 1fr; } .score-card { grid-template-columns: auto 1fr; } .signal { grid-column: 1 / -1; display: flex; justify-content: space-between; text-align: left; } .card-pad { padding: 16px; } .gauge { width: 78px; height: 78px; } .metric-row { grid-template-columns: 88px 1fr 48px; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; } }
@media (prefers-color-scheme: dark) {
  :root { --primary: #6f95ff; --primary-2: #75a0ff; --accent: #f1a33c; --bg: #08111f; --surface: #101c2d; --surface-2: #19283d; --text: #edf4ff; --muted: #aebdd0; --border: #2c405a; --good: #5ee6ae; --warn: #f5c45c; --bad: #ff8c8c; --focus: #8db2ff; --shadow: 0 10px 30px rgba(0,0,0,.25); }
}
</style>
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _pct(value: float, digits: int = 1) -> str:
    return "—" if pd.isna(value) else f"{value:.{digits}%}"


def _score_color(score: float) -> str:
    if score >= 80:
        return "var(--good)"
    if score >= 55:
        return "var(--accent)"
    return "var(--primary-2)" if score >= 40 else "var(--bad)"


def _score_card(row: pd.Series, selected: str) -> str:
    symbol = str(row["symbol"])
    active = symbol == selected
    current = ' aria-current="page"' if active else ""
    selected_class = " selected" if active else ""
    return f"""
    <a class="card score-card{selected_class}" href="/?symbol={_e(symbol)}" aria-label="查看 {_e(symbol)} 详情"{current}>
      <div class="gauge" style="--score:{float(row['total_score']):.1f};--gauge-color:{_score_color(float(row['total_score']))}" aria-label="评分 {float(row['total_score']):.0f} 分，满分 100">
        <span class="gauge-value">{float(row['total_score']):.0f}<small>/ 100</small></span>
      </div>
      <div>
        <p class="symbol">{_e(symbol)}</p>
        <span class="state">{_e(row['market_state'])}</span>
        <p class="price">{float(row['close']):,.2f}</p>
      </div>
      <div class="signal"><strong>{_e(row['signal'])}</strong><span>Investment Signal</span></div>
    </a>"""


def _component_row(label: str, value: float, maximum: float) -> str:
    width = max(0, min(100, value / maximum * 100))
    return f"""<div class="metric-row">
      <label>{_e(label)}</label><div class="track" role="progressbar" aria-label="{_e(label)}" aria-valuemin="0" aria-valuemax="{maximum:.0f}" aria-valuenow="{value:.0f}"><span style="width:{width:.1f}%"></span></div>
      <strong>{value:.0f}/{maximum:.0f}</strong>
    </div>"""


def render_score_chart(frames: dict[str, pd.DataFrame], selected: str) -> str:
    nonempty = [frame for frame in frames.values() if not frame.empty]
    if not nonempty:
        return '<div class="empty">暂无历史评分数据。</div>'
    max_date = max(pd.to_datetime(frame["date"]).max() for frame in nonempty)
    cutoff = max_date - timedelta(days=730)
    width, height, left, right, top, bottom = 900, 310, 48, 18, 18, 36
    plot_w, plot_h = width - left - right, height - top - bottom
    all_dates = pd.concat([pd.to_datetime(f["date"]) for f in nonempty])
    min_date = max(cutoff, all_dates.min())
    span = max((max_date - min_date).days, 1)

    def x_at(value: pd.Timestamp) -> float:
        return left + (value - min_date).days / span * plot_w

    def y_at(value: float) -> float:
        return top + (100 - value) / 100 * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="score-chart-title score-chart-desc">',
             '<title id="score-chart-title">QQQ 与 SPY 最近两年 Investment Score</title>',
             '<desc id="score-chart-desc">纵轴为零到一百分，折线展示每日评分趋势，七十分以上进入机会区域。</desc>',
             f'<rect x="{left}" y="{y_at(100):.1f}" width="{plot_w}" height="{y_at(70)-y_at(100):.1f}" fill="var(--good)" opacity=".07"/>']
    for tick in (0, 20, 40, 60, 80, 100):
        y = y_at(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="var(--border)" stroke-width="1"/>')
        parts.append(f'<text x="{left-9}" y="{y+4:.1f}" text-anchor="end" fill="var(--muted)" font-size="11">{tick}</text>')
    for months in (24, 18, 12, 6, 0):
        tick_date = max_date - pd.DateOffset(months=months)
        if tick_date >= min_date:
            x = x_at(tick_date)
            parts.append(f'<text x="{x:.1f}" y="{height-10}" text-anchor="middle" fill="var(--muted)" font-size="11">{tick_date:%Y-%m}</text>')
    styles = {"QQQ": ("var(--primary-2)", ""), "SPY": ("var(--accent)", "8 5")}
    for symbol in ("QQQ", "SPY"):
        frame = frames.get(symbol, pd.DataFrame())
        if frame.empty:
            continue
        visible = frame.assign(_date=pd.to_datetime(frame["date"]))
        visible = visible.loc[visible["_date"] >= min_date]
        points = " ".join(f"{x_at(row['_date']):.1f},{y_at(float(row['total_score'])):.1f}" for _, row in visible.iterrows())
        color, dash = styles[symbol]
        opacity = "1" if symbol == selected else ".55"
        stroke_width = "3" if symbol == selected else "2"
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-dasharray="{dash}" opacity="{opacity}" vector-effect="non-scaling-stroke"/>')
    parts.append("</svg>")
    return "".join(parts)


def _backtest_table(scores: pd.DataFrame, symbol: str) -> str:
    summary = summarize_thresholds(add_forward_returns(scores), symbol)
    rows = []
    for _, row in summary.iterrows():
        rows.append("<tr>" + "".join((
            f"<td>≥ {int(row['threshold'])}</td>", f"<td>{int(row['count']):,}</td>",
            f"<td>{_pct(row['avg_20d'])}</td>", f"<td>{_pct(row['win_rate_20d'], 0)}</td>",
            f"<td>{_pct(row['avg_60d'])}</td>", f"<td>{_pct(row['win_rate_60d'], 0)}</td>",
            f"<td>{_pct(row['avg_120d'])}</td>", f"<td>{_pct(row['avg_250d'])}</td>",
        )) + "</tr>")
    return """<div class="table-scroll"><table>
      <thead><tr><th>评分阈值</th><th>样本</th><th>平均 20D</th><th>20D 胜率</th><th>平均 60D</th><th>60D 胜率</th><th>平均 120D</th><th>平均 250D</th></tr></thead>
      <tbody>""" + "".join(rows) + "</tbody></table></div>"


def _recent_table(frames: dict[str, pd.DataFrame]) -> str:
    rows = []
    for symbol, frame in frames.items():
        for _, row in frame.tail(8).iloc[::-1].iterrows():
            rows.append((str(row["date"]), symbol, float(row["total_score"]), str(row["market_state"]), str(row["signal"]), float(row["close"])))
    rows.sort(reverse=True)
    body = "".join(f"<tr><td>{_e(d)}</td><td>{_e(s)}</td><td>{score:.0f}</td><td>{_e(state)}</td><td>{_e(signal)}</td><td>{close:,.2f}</td></tr>" for d, s, score, state, signal, close in rows)
    return """<div class="table-scroll"><table><thead><tr><th>日期</th><th>标的</th><th>评分</th><th>状态</th><th>信号</th><th>收盘价</th></tr></thead><tbody>""" + body + "</tbody></table></div>"


def _database_counts() -> tuple[int, int, int]:
    with connect() as connection:
        market = connection.execute("SELECT COUNT(*) FROM market_daily").fetchone()[0]
        macro = connection.execute("SELECT COUNT(*) FROM macro_daily").fetchone()[0]
        scores = connection.execute("SELECT COUNT(*) FROM investment_score").fetchone()[0]
    return market, macro, scores


def _data_sources_panel() -> str:
    with connect() as connection:
        market_rows = connection.execute(
            "SELECT symbol AS name, MIN(date) AS first_date, MAX(date) AS last_date, "
            "COUNT(*) AS row_count FROM market_daily GROUP BY symbol"
        ).fetchall()
        macro_rows = connection.execute(
            "SELECT series AS name, MIN(date) AS first_date, MAX(date) AS last_date, "
            "COUNT(*) AS row_count FROM macro_daily GROUP BY series"
        ).fetchall()
    coverage = {row["name"]: row for row in (*market_rows, *macro_rows)}
    provider = settings.market_data_provider.lower()
    if provider == "yahoo":
        equity_source = "Yahoo Finance"
        equity_urls = {
            "QQQ": "https://finance.yahoo.com/quote/QQQ/history/",
            "SPY": "https://finance.yahoo.com/quote/SPY/history/",
        }
    else:
        equity_source = "Nasdaq Historical"
        equity_urls = {
            "QQQ": "https://www.nasdaq.com/market-activity/etf/qqq/historical",
            "SPY": "https://www.nasdaq.com/market-activity/etf/spy/historical",
        }
    sources = (
        ("QQQ", equity_source, "QQQ", equity_urls["QQQ"]),
        ("SPY", equity_source, "SPY", equity_urls["SPY"]),
        ("VIX", "CBOE via FRED", "VIXCLS", "https://fred.stlouisfed.org/series/VIXCLS"),
        ("US10Y", "Federal Reserve via FRED", "DGS10", "https://fred.stlouisfed.org/series/DGS10"),
        ("US2Y", "Federal Reserve via FRED", "DGS2", "https://fred.stlouisfed.org/series/DGS2"),
    )
    rows = []
    for name, source, series_code, url in sources:
        stats = coverage.get(name)
        first_date = stats["first_date"] if stats else "—"
        last_date = stats["last_date"] if stats else "—"
        row_count = f"{stats['row_count']:,}" if stats else "0"
        rows.append(
            f'<tr><td><strong>{_e(name)}</strong></td><td><a href="{_e(url)}" '
            f'target="_blank" rel="noopener noreferrer">{_e(source)}</a></td>'
            f'<td>{_e(series_code)}</td><td>{_e(first_date)} → {_e(last_date)}</td>'
            f'<td>{row_count}</td></tr>'
        )
    return f"""<section id="data-sources" class="card card-pad source-panel" hidden>
      <div class="section-head"><div><p class="eyebrow">Data provenance</p><h2>数据来源与本地覆盖</h2><p class="meta">来源名称可打开对应的官方数据页面。</p></div></div>
      <div class="table-scroll"><table><thead><tr><th>数据</th><th>来源</th><th>标的 / 系列</th><th>本地覆盖区间</th><th>记录数</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
      <p class="source-note">当前股票行情 Provider：{_e(provider)}。VIX 为 CBOE 日收盘指数，经 FRED 发布；DGS10/DGS2 为美国国债固定期限收益率，单位为百分比、日频、未经季调。</p>
    </section>"""


def _run_full_update() -> bool:
    """Run the same sync/score/report workflow as ``run.bat`` (daily)."""
    if not sync_data():
        return False
    latest_rows = []
    for symbol in ("QQQ", "SPY"):
        latest_rows.append(calculate_symbol_scores(symbol).iloc[-1])
    generate_daily_report(pd.DataFrame(latest_rows), BASE_DIR / "output/reports")
    return True


def _update_feedback(status: str | None) -> str:
    if status == "success":
        return '<div class="notice success" role="status"><div><strong>更新完成：</strong> 行情、宏观数据、QQQ/SPY 评分和日报均已重新生成。</div></div>'
    if status == "error":
        return '<div class="notice error" role="alert"><div><strong>更新失败：</strong> 评分未重新生成，请查看启动窗口日志后重试。系统不会生成假评分。</div></div>'
    if status == "busy":
        return '<div class="notice" role="status"><div><strong>正在更新：</strong> 已有更新任务运行中，请稍后再试。</div></div>'
    return ""


def build_dashboard_page(selected: str = "QQQ", update_status: str | None = None) -> str:
    selected = selected if selected in {"QQQ", "SPY"} else "QQQ"
    frames = {symbol: get_score_data(symbol) for symbol in ("QQQ", "SPY")}
    if any(frame.empty for frame in frames.values()):
        missing = ", ".join(symbol for symbol, frame in frames.items() if frame.empty)
        main_content = f'<section class="card empty"><h2>暂无完整评分数据</h2><p>缺少 {_e(missing)}。请先运行 <code>run.bat</code> 完成数据同步和评分。</p></section>'
        date_label = "尚未计算"
    else:
        latest = {symbol: frame.iloc[-1] for symbol, frame in frames.items()}
        row = latest[selected]
        date_label = str(max(value["date"] for value in latest.values()))
        market_count, macro_count, score_count = _database_counts()
        cards = "".join(_score_card(latest[symbol], selected) for symbol in ("QQQ", "SPY"))
        components = "".join((
            _component_row("Trend", float(row["trend_score"]), 35),
            _component_row("Drawdown", float(row["drawdown_score"]), 25),
            _component_row("Risk", float(row["risk_score"]), 20),
            _component_row("Macro", float(row["macro_score"]), 20),
        ))
        chart = render_score_chart(frames, selected)
        main_content = f"""
        <section class="grid hero-grid" aria-label="最新评分">{cards}</section>
        <div class="notice"><div><strong>读数说明：</strong> 高分代表规则模型中的长期投资赔率改善，不等同于即时交易指令；Signal 还包含趋势确认和风险保护。</div></div>
        <section class="grid main-grid">
          <article class="card card-pad">
            <div class="section-head"><div><p class="eyebrow">Score history</p><h2>最近两年评分趋势</h2></div><div class="legend" aria-label="图例"><span><i></i>QQQ 实线</span><span><i class="spy"></i>SPY 虚线</span></div></div>
            <div class="chart-wrap">{chart}</div>
            <details><summary>查看近期评分数据表</summary>{_recent_table(frames)}</details>
          </article>
          <aside class="card card-pad">
            <p class="eyebrow">{_e(selected)} breakdown</p><h2>评分构成</h2>
            <div class="metric-list">{components}</div>
            <div class="grid facts">
              <div class="fact"><span>52W 回撤</span><strong>{_pct(float(row['drawdown']))}</strong></div>
              <div class="fact"><span>VIX</span><strong>{float(row['vix']):.2f}</strong></div>
              <div class="fact"><span>US10Y</span><strong>{float(row['us10y']):.2f}%</strong></div>
              <div class="fact"><span>US2Y</span><strong>{float(row['us2y']):.2f}%</strong></div>
            </div>
            <div class="facts grid">
              <div class="fact"><span>行情记录</span><strong>{market_count:,}</strong></div>
              <div class="fact"><span>宏观记录</span><strong>{macro_count:,}</strong></div>
              <div class="fact"><span>评分记录</span><strong>{score_count:,}</strong></div>
              <div class="fact"><span>数据模式</span><strong>LOCAL</strong></div>
            </div>
          </aside>
        </section>
        <section class="card card-pad table-card">
          <div class="section-head"><div><p class="eyebrow">Forward returns</p><h2>{_e(selected)} 高分样本回测</h2><p class="meta">收益只用于评价历史评分，不参与当日 Score。</p></div></div>
          {_backtest_table(frames[selected], selected)}
        </section>"""

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="QQQ 与 SPY Investment Score 本地仪表盘"><title>Investment Score Dashboard</title>{STYLE}</head>
    <body><a class="skip" href="#main">跳到主要内容</a><div class="shell">
      <header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V9m5 10V5m5 14v-7m5 7V3"/><path d="M3 21h18"/></svg></span><div><h1>Investment Score</h1><p class="meta">V0.1 · 数据日期 {_e(date_label)}</p></div></div>
      <nav class="actions" aria-label="仪表盘操作"><div class="segmented"><a href="/?symbol=QQQ" {'aria-current="page"' if selected == 'QQQ' else ''}>QQQ</a><a href="/?symbol=SPY" {'aria-current="page"' if selected == 'SPY' else ''}>SPY</a></div><button id="source-toggle" class="button" type="button" aria-expanded="false" aria-controls="data-sources">数据来源</button><form id="update-form" action="/update?symbol={_e(selected)}" method="post"><button id="update-button" class="button primary" type="submit"><span class="button-label">更新数据</span></button></form><span id="update-status" class="sr-only" aria-live="polite"></span></nav></header>
      <main id="main">{_update_feedback(update_status)}{_data_sources_panel()}{main_content}</main><footer>本页面读取本机 SQLite 数据，仅供规则研究，不构成投资建议。</footer>
    </div><script>const sourceToggle=document.getElementById('source-toggle');const sourcePanel=document.getElementById('data-sources');sourceToggle?.addEventListener('click',()=>{{const willOpen=sourcePanel.hidden;sourcePanel.hidden=!willOpen;sourceToggle.setAttribute('aria-expanded',String(willOpen));sourceToggle.textContent=willOpen?'隐藏来源':'数据来源';}});const form=document.getElementById('update-form');form?.addEventListener('submit',()=>{{const button=document.getElementById('update-button');button.disabled=true;button.classList.add('updating');button.querySelector('.button-label').textContent='正在更新';document.getElementById('update-status').textContent='正在联网同步数据并重新计算评分，请稍候。';}});</script></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/favicon.ico":
            payload, content_type, status = b"", "image/x-icon", 204
        elif parsed.path == "/health":
            payload, content_type, status = b"ok", "text/plain; charset=utf-8", 200
        elif parsed.path == "/":
            query = parse_qs(parsed.query)
            selected = query.get("symbol", ["QQQ"])[0].upper()
            update_status = query.get("update", [None])[0]
            try:
                payload = build_dashboard_page(selected, update_status).encode("utf-8")
                content_type, status = "text/html; charset=utf-8", 200
            except Exception as exc:
                LOG.exception("Dashboard rendering failed: %s", exc)
                payload = f"Dashboard rendering failed: {_e(exc)}".encode("utf-8")
                content_type, status = "text/plain; charset=utf-8", 500
        else:
            payload, content_type, status = b"Not found", "text/plain; charset=utf-8", 404
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/update":
            self.send_error(404)
            return
        selected = parse_qs(parsed.query).get("symbol", ["QQQ"])[0].upper()
        selected = selected if selected in {"QQQ", "SPY"} else "QQQ"
        if not UPDATE_LOCK.acquire(blocking=False):
            self._redirect(f"/?symbol={selected}&update=busy")
            return
        try:
            LOG.info("Dashboard data update started")
            outcome = "success" if _run_full_update() else "error"
            LOG.info("Dashboard data update finished: %s", outcome)
        except Exception as exc:
            LOG.exception("Dashboard data update failed: %s", exc)
            outcome = "error"
        finally:
            UPDATE_LOCK.release()
        self._redirect(f"/?symbol={selected}&update={outcome}")

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        LOG.info(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Investment Score dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Render once and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.check:
        page = build_dashboard_page()
        print(f"Dashboard render OK: {len(page):,} characters")
        return 0
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Investment Score Dashboard: {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
