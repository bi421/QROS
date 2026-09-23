import glob
import os
import traceback

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")


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
    # Pandas 2.0+ дээр 'h' (жижиг үсэг) ашиглах
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
async def dashboard(request: Request):
    try:
        df = load_data()
        result = run_backtest(df)
        if result is None:
            return HTMLResponse("<h1>❌ Бэктест хийхэд хангалттай өгөгдөл байхгүй байна.</h1>")

        # Charts
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

        # Drawdown
        dd = (result["equity"].cummax() - result["equity"]) / result["equity"].cummax() * 100
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=result.index, y=dd, mode="lines", fill="tozeroy", name="Drawdown"))
        fig_dd.update_layout(title="Drawdown", xaxis_title="Date", yaxis_title="%", height=300)
        dd_html = fig_dd.to_html(full_html=False, include_plotlyjs="cdn")

        # Stats
        returns = result["strategy_returns"].dropna()
        winrate = (returns > 0).sum() / returns.count() * 100 if returns.count() > 0 else 0
        total_return = (result["equity"].iloc[-1] / 10000 - 1) * 100
        sharpe = returns.mean() / returns.std() * (252 * 6.5 * 12) ** 0.5 if returns.std() != 0 else 0
        max_dd = dd.max()

        stats = {
            "winrate": f"{winrate:.2f}%",
            "return": f"{total_return:.2f}%",
            "sharpe": f"{sharpe:.2f}",
            "drawdown": f"{max_dd:.2f}%",
            "trades": str(returns.count()),
            "period": f"{result.index[0].strftime('%Y-%m-%d')} → {result.index[-1].strftime('%Y-%m-%d')}",
        }

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "equity": equity_html,
                "sma": sma_html,
                "dd": dd_html,
                "stats": stats,
            },
        )
    except Exception:
        return HTMLResponse(f"<h1>❌ Алдаа</h1><pre>{traceback.format_exc()}</pre>")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
