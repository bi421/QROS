import glob
import traceback

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


def load_data():
    files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
    if not files:
        # Жишээ өгөгдөл
        dates = pd.date_range("2024-01-01", "2025-01-01", freq="1h")
        np.random.seed(42)
        price = 2000 + np.cumsum(np.random.randn(len(dates)) * 3)
        df = pd.DataFrame(
            {
                "open": price + np.random.randn(len(dates)) * 2,
                "high": price + np.abs(np.random.randn(len(dates)) * 4) + 2,
                "low": price - np.abs(np.random.randn(len(dates)) * 4) - 2,
                "close": price,
                "volume": np.random.randint(100, 1000, len(dates)),
            },
            index=dates,
        )
        return df

    df = pd.concat(
        [
            pd.read_csv(
                f,
                sep=";",
                header=None,
                names=["datetime", "open", "high", "low", "close", "volume"],
                dtype={"datetime": str},
            )
            for f in files
        ],
        ignore_index=True,
    )
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
    df = df.set_index("datetime")
    return df


def run_backtest(df, timeframe="1h", short=20, long=50):
    df_h = df.resample(timeframe).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

    if len(df_h) < long:
        return None

    df_h["SMA_short"] = df_h["close"].rolling(short).mean()
    df_h["SMA_long"] = df_h["close"].rolling(long).mean()
    df_h["signal"] = 0
    df_h.loc[df_h["SMA_short"] > df_h["SMA_long"], "signal"] = 1
    df_h.loc[df_h["SMA_short"] <= df_h["SMA_long"], "signal"] = -1
    df_h["returns"] = df_h["close"].pct_change()
    df_h["strategy_returns"] = df_h["returns"] * df_h["signal"].shift(1)
    df_h["equity"] = (1 + df_h["strategy_returns"]).cumprod() * 10000
    return df_h


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    try:
        df = load_data()
        result = run_backtest(df)
        if result is None:
            return HTMLResponse("<h1>❌ Бэктест хийхэд хангалттай өгөгдөл байхгүй байна.</h1>")

        # График үүсгэх
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=result.index, y=result["equity"], mode="lines", name="Equity"))
        fig_equity.update_layout(title="Equity Curve", xaxis_title="Date", yaxis_title="Equity ($)", height=400)
        equity_html = fig_equity.to_html(full_html=False, include_plotlyjs="cdn")

        fig_sma = go.Figure()
        fig_sma.add_trace(go.Scatter(x=result.index, y=result["close"], mode="lines", name="Price"))
        fig_sma.add_trace(go.Scatter(x=result.index, y=result["SMA_short"], mode="lines", name="SMA 20"))
        fig_sma.add_trace(go.Scatter(x=result.index, y=result["SMA_long"], mode="lines", name="SMA 50"))
        fig_sma.update_layout(title="Price & SMA", xaxis_title="Date", height=400)
        sma_html = fig_sma.to_html(full_html=False, include_plotlyjs="cdn")

        dd = (result["equity"].cummax() - result["equity"]) / result["equity"].cummax() * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=result.index, y=dd, mode="lines", fill="tozeroy", name="Drawdown"))
        fig_dd.update_layout(title="Drawdown", xaxis_title="Date", yaxis_title="%", height=300)
        dd_html = fig_dd.to_html(full_html=False, include_plotlyjs="cdn")

        # Статистик
        returns = result["strategy_returns"].dropna()
        winrate = (returns > 0).sum() / returns.count() * 100 if returns.count() > 0 else 0
        total_return = (result["equity"].iloc[-1] / 10000 - 1) * 100
        sharpe = returns.mean() / returns.std() * (252 * 6.5 * 12) ** 0.5 if returns.std() != 0 else 0
        max_dd = dd.max()

        # HTML
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ResearchOS</title>
    <style>
        body {{ font-family: Arial; background: #f4f6f9; padding: 20px; }}
        .container {{ max-width: 1200px; margin: auto; }}
        h1 {{ color: #2c3e50; }}
        .card {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px; }}
        .stat-item {{ background: #f8f9fa; padding: 12px 16px; border-radius: 6px; border-left: 4px solid #3498db; }}
        .stat-item .label {{ font-size: 11px; color: #7f8c8d; text-transform: uppercase; }}
        .stat-item .value {{ font-size: 20px; font-weight: bold; color: #2c3e50; }}
        .stat-item .value.positive {{ color: #27ae60; }}
        .stat-item .value.negative {{ color: #e74c3c; }}
        .chart {{ width: 100%; overflow: hidden; }}
        .chart iframe {{ width: 100%; border: none; height: 420px; }}
        .footer {{ text-align: center; color: #95a5a6; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 ResearchOS Dashboard</h1>
        <div class="card">
            <h3>📈 Statistics</h3>
            <div class="stats-grid">
                <div class="stat-item"><div class="label">Winrate</div><div class="value">{winrate:.2f}%</div></div>
                <div class="stat-item"><div class="label">Total Return</div><div class="value {"positive" if total_return >= 0 else "negative"}">{total_return:.2f}%</div></div>
                <div class="stat-item"><div class="label">Sharpe</div><div class="value">{sharpe:.2f}</div></div>
                <div class="stat-item"><div class="label">Max Drawdown</div><div class="value negative">{max_dd:.2f}%</div></div>
                <div class="stat-item"><div class="label">Trades</div><div class="value">{returns.count()}</div></div>
                <div class="stat-item"><div class="label">Period</div><div class="value" style="font-size:14px;">{result.index[0].strftime("%Y-%m-%d")} → {result.index[-1].strftime("%Y-%m-%d")}</div></div>
            </div>
        </div>
        <div class="card"><h3>📈 Equity</h3><div class="chart">{equity_html}</div></div>
        <div class="card"><h3>📊 Price & SMA</h3><div class="chart">{sma_html}</div></div>
        <div class="card"><h3>📉 Drawdown</h3><div class="chart">{dd_html}</div></div>
        <div class="footer">ResearchOS © 2026</div>
    </div>
</body>
</html>
"""
        return HTMLResponse(html)
    except Exception:
        return HTMLResponse(f"<h1>❌ Алдаа</h1><pre>{traceback.format_exc()}</pre>")


if __name__ == "__main__":
    print("🚀 Dashboard эхлүүлж байна...")
    print("🌐 http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
