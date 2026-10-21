"""رسوم Plotly موحّدة الشكل (وضع داكن، محور واحد، شبكة خفيفة، تلميحات عند المرور)."""
import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import COLORS as C

FONT = "Tajawal, system-ui, sans-serif"
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo
# قطب الربح أزرق وقطب الخسارة أحمر ومنتصف رمادي (آمن لعمى الألوان)
DIVERGING = [[0.0, C["red"]], [0.5, C["neutral"]], [1.0, C["blue"]]]


def _base(fig, height):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36, b=8),
        paper_bgcolor=C["surface"], plot_bgcolor=C["surface"],
        font=dict(family=FONT, color=C["text"], size=13),
        hoverlabel=dict(font=dict(family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=C["grid"], linecolor=C["axis"], zeroline=False, showspikes=True,
                     spikecolor=C["muted"], spikethickness=1, spikedash="solid", spikemode="across")
    fig.update_yaxes(gridcolor=C["grid"], linecolor=C["axis"], zeroline=False)
    return fig


def _naive(idx):
    idx = pd.DatetimeIndex(idx)
    return idx.tz_localize(None) if idx.tz is not None else idx


def price_chart(d, levels=None, trades=None, sup=(), res=(), intraday=False, bars=150):
    """شموع + VWAP + متوسطات + مستويات الصفقة + فوليوم + RSI + MACD."""
    d = d.tail(bars)
    x = _naive(d.index)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.025,
                        row_heights=[0.56, 0.12, 0.16, 0.16])
    fig.add_trace(go.Candlestick(
        x=x, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="السعر",
        increasing=dict(line=dict(color=C["good"], width=1), fillcolor=C["good"]),
        decreasing=dict(line=dict(color=C["critical"], width=1), fillcolor=C["critical"])), 1, 1)
    for col, name, color, dash in (("VWAP", "VWAP", C["orange"], "solid"),
                                   ("SMA50", "SMA 50", C["violet"], "solid"),
                                   ("SMA200", "SMA 200", C["aqua"], "solid")):
        if col in d and d[col].notna().any():
            fig.add_trace(go.Scatter(x=x, y=d[col], mode="lines", name=name,
                                     line=dict(color=color, width=1.6, dash=dash)), 1, 1)

    for lvl in (levels or []):
        fig.add_hline(y=lvl["y"], line_dash=lvl.get("dash", "dash"), line_color=lvl["color"],
                      line_width=1.4, annotation_text=lvl["label"], annotation_position="top left",
                      annotation_font_color=lvl["color"], row=1, col=1)
    for y in sup:
        fig.add_hline(y=y, line_dash="dot", line_color=C["muted"], line_width=1,
                      annotation_text="دعم " + format(y, ",.2f"), annotation_position="bottom right",
                      annotation_font_color=C["muted"], row=1, col=1)
    for y in res:
        fig.add_hline(y=y, line_dash="dot", line_color=C["muted"], line_width=1,
                      annotation_text="مقاومة " + format(y, ",.2f"), annotation_position="top right",
                      annotation_font_color=C["muted"], row=1, col=1)

    if trades is not None and not trades.empty:
        lo, hi = x.min(), x.max()
        t = trades.copy()
        for col in ("opened_dt", "closed_dt"):
            s = t[col].dt.tz_localize(LOCAL_TZ).dt.tz_convert("America/New_York").dt.tz_localize(None)
            t[col] = s if intraday else s.dt.normalize()
        t = t[(t["opened_dt"] >= lo) | (t["closed_dt"] >= lo)]
        t = t[t["opened_dt"] <= hi]
        if not t.empty:
            fig.add_trace(go.Scatter(
                x=t["opened_dt"], y=t["entry"], mode="markers", name="دخول سابق",
                marker=dict(symbol="triangle-up", size=12, color=C["blue"],
                            line=dict(color="#0E1117", width=2)),
                hovertemplate="دخول $%{y:,.2f}<extra></extra>"), 1, 1)
            fig.add_trace(go.Scatter(
                x=t["closed_dt"], y=t["exit"], mode="markers", name="خروج سابق",
                marker=dict(symbol="x", size=11,
                            color=np.where(t["pnl"] > 0, C["good"], C["critical"]),
                            line=dict(color="#0E1117", width=1)),
                customdata=np.stack([t["pnl"], t["reason"]], axis=-1),
                hovertemplate="خروج $%{y:,.2f}<br>%{customdata[1]}<br>$%{customdata[0]:+,.2f}<extra></extra>"),
                1, 1)

    up = d["Close"] >= d["Open"]
    fig.add_trace(go.Bar(x=x, y=d["Volume"], name="الفوليوم", showlegend=False, opacity=0.55,
                         marker_color=np.where(up, C["good"], C["critical"])), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=d["RSI"], mode="lines", name="RSI", showlegend=False,
                             line=dict(color=C["blue"], width=1.6)), 3, 1)
    for y in (70, 30):
        fig.add_hline(y=y, line_color=C["axis"], line_width=1, row=3, col=1)
    fig.add_trace(go.Bar(x=x, y=d["MACD_hist"], name="MACD hist", showlegend=False,
                         marker_color=np.where(d["MACD_hist"] >= 0, C["good"], C["critical"]),
                         opacity=0.6), 4, 1)
    fig.add_trace(go.Scatter(x=x, y=d["MACD"], mode="lines", name="MACD", showlegend=False,
                             line=dict(color=C["blue"], width=1.4)), 4, 1)
    fig.add_trace(go.Scatter(x=x, y=d["MACD_sig"], mode="lines", name="Signal", showlegend=False,
                             line=dict(color=C["orange"], width=1.4)), 4, 1)

    _base(fig, 680)
    fig.update_layout(hovermode="x unified", xaxis_rangeslider_visible=False, bargap=0.15)
    breaks = [dict(bounds=["sat", "mon"])]
    if intraday:
        breaks.append(dict(bounds=[16, 9.5], pattern="hour"))
    if intraday or (len(x) > 1 and (x[1] - x[0]) <= pd.Timedelta(days=1)):
        fig.update_xaxes(rangebreaks=breaks)
    fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])
    fig.update_yaxes(title_text="MACD", row=4, col=1)
    fig.update_yaxes(title_text="فوليوم", row=2, col=1)
    return fig


def equity_vs_benchmark(curve, bench=None, name="المحفظة", bench_name="SPY"):
    """الاثنين مفهرسين على 100 بنفس المحور (بدون محورين)."""
    fig = go.Figure()
    if curve.empty:
        return _base(fig, 320)
    base = curve / curve.iloc[0] * 100
    fig.add_trace(go.Scatter(x=base.index, y=base.values, mode="lines", name=name,
                             line=dict(color=C["blue"], width=2),
                             hovertemplate="%{y:.1f}<extra>" + name + "</extra>"))
    if bench is not None and not bench.empty:
        b = bench[(bench.index >= curve.index[0]) & (bench.index <= curve.index[-1])]
        if len(b) > 1:
            b = b / b.iloc[0] * 100
            fig.add_trace(go.Scatter(x=b.index, y=b.values, mode="lines", name=bench_name,
                                     line=dict(color=C["orange"], width=2),
                                     hovertemplate="%{y:.1f}<extra>" + bench_name + "</extra>"))
    _base(fig, 340)
    fig.update_layout(hovermode="x unified", yaxis_title="مؤشر (البداية = 100)")
    return fig


def drawdown_chart(dd):
    fig = go.Figure()
    if not dd.empty:
        fig.add_trace(go.Scatter(x=dd.index, y=dd.values, mode="lines", name="التراجع %",
                                 fill="tozeroy", line=dict(color=C["critical"], width=1.6),
                                 fillcolor="rgba(208,59,59,0.18)",
                                 hovertemplate="%{y:.2f}%<extra></extra>"))
    _base(fig, 240)
    fig.update_layout(hovermode="x unified", showlegend=False, yaxis_title="التراجع %")
    return fig


def monthly_heatmap(table):
    z = table.values.astype(float)
    lim = np.nanmax(np.abs(z)) if np.isfinite(z).any() else 1.0
    text = [["" if not np.isfinite(v) else "{:+,.0f}".format(v) for v in row] for row in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=[str(m) for m in table.columns], y=[str(y) for y in table.index],
        colorscale=DIVERGING, zmid=0, zmin=-lim, zmax=lim, text=text, texttemplate="%{text}",
        xgap=2, ygap=2, colorbar=dict(title="$"),
        hovertemplate="سنة %{y} / شهر %{x}<br>$%{z:+,.2f}<extra></extra>"))
    _base(fig, 120 + 46 * max(1, len(table)))
    fig.update_xaxes(title_text="الشهر", type="category", showspikes=False, showgrid=False)
    fig.update_yaxes(type="category", showgrid=False)
    return fig


def signed_bars(labels, values, horizontal=False, height=300, fmt="$%{y:+,.2f}"):
    colors = [C["blue"] if v >= 0 else C["red"] for v in values]
    if horizontal:
        bar = go.Bar(y=labels, x=values, orientation="h", marker_color=colors,
                     hovertemplate="%{y}: " + fmt.replace("%{y", "%{x") + "<extra></extra>")
    else:
        bar = go.Bar(x=labels, y=values, marker_color=colors,
                     hovertemplate="%{x}: " + fmt + "<extra></extra>")
    fig = go.Figure(bar)
    _base(fig, height)
    fig.update_layout(showlegend=False, bargap=0.25)
    return fig


def r_histogram(rs):
    fig = go.Figure(go.Histogram(x=rs, nbinsx=30, marker_color=C["blue"], opacity=0.85,
                                 marker_line=dict(color="#0E1117", width=2),
                                 hovertemplate="R %{x}<br>%{y} صفقة<extra></extra>"))
    fig.add_vline(x=0, line_color=C["muted"], line_width=1)
    _base(fig, 280)
    fig.update_layout(showlegend=False, xaxis_title="R لكل صفقة", yaxis_title="عدد الصفقات")
    return fig


def line(series, name, color=None, height=300, ytitle=None):
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", name=name,
                               line=dict(color=color or C["blue"], width=2),
                               hovertemplate="%{y:,.2f}<extra>" + name + "</extra>"))
    _base(fig, height)
    fig.update_layout(hovermode="x unified", showlegend=False, yaxis_title=ytitle)
    return fig


def grid_heatmap(df):
    z = df.values.astype(float)
    lim = np.nanmax(np.abs(z)) if np.isfinite(z).any() else 1.0
    text = [["-" if not np.isfinite(v) else "{:+.3f}".format(v) for v in row] for row in z]
    fig = go.Figure(go.Heatmap(z=z, x=list(df.columns), y=list(df.index), colorscale=DIVERGING,
                               zmid=0, zmin=-lim, zmax=lim, text=text, texttemplate="%{text}",
                               xgap=2, ygap=2, colorbar=dict(title="R"),
                               hovertemplate="%{y} / %{x}<br>%{z:+.3f}R<extra></extra>"))
    _base(fig, 300)
    fig.update_xaxes(showspikes=False, showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig
