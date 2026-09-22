import asyncio
import glob
import json
from datetime import datetime

import pandas as pd
import plotly.graph_objs as go
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

# Manual Setup Router
from researchos.dashboard.manual_setup import router as manual_router

app = FastAPI()
app.include_router(manual_router)


def get_data_and_signals():
    files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
    if not files:
        return None, None, None, None, None

    df = pd.concat([pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files], ignore_index=True)
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
    df = df.set_index("datetime")
    df_h = df.resample("4h").agg({"close": "last"}).dropna()

    close = df_h["close"]
    sma20 = close.rolling(20).mean()
    sma100 = close.rolling(100).mean()

    buy_signals = []
    sell_signals = []
    for i in range(1, len(df_h)):
        if sma20.iloc[i] > sma100.iloc[i] and sma20.iloc[i - 1] <= sma100.iloc[i - 1]:
            buy_signals.append((df_h.index[i], close.iloc[i]))
        elif sma20.iloc[i] < sma100.iloc[i] and sma20.iloc[i - 1] >= sma100.iloc[i - 1]:
            sell_signals.append((df_h.index[i], close.iloc[i]))

    return df_h, sma20, sma100, buy_signals, sell_signals


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    df, sma20, sma100, buys, sells = get_data_and_signals()
    if df is None:
        return HTMLResponse("<h1>No data found. Please check data path.</h1>")

    fig = go.Figure()

    fig.add_trace(go.Scatter(x=df.index, y=df["close"], name="Close Price", line=dict(color="blue", width=1.5)))

    fig.add_trace(go.Scatter(x=df.index, y=sma20, name="SMA20", line=dict(color="orange", width=2, dash="dash")))

    fig.add_trace(go.Scatter(x=df.index, y=sma100, name="SMA100", line=dict(color="red", width=2, dash="dash")))

    if buys:
        fig.add_trace(go.Scatter(x=[b[0] for b in buys], y=[b[1] for b in buys], mode="markers", name="BUY", marker=dict(symbol="triangle-up", size=15, color="limegreen")))

    if sells:
        fig.add_trace(go.Scatter(x=[s[0] for s in sells], y=[s[1] for s in sells], mode="markers", name="SELL", marker=dict(symbol="triangle-down", size=15, color="red")))

    fig.update_layout(title="XAUUSD 4h - SMA20/100 Crossover Strategy", xaxis_title="Date", yaxis_title="Price (USD)", template="plotly_dark", hovermode="x unified", legend=dict(x=0.02, y=0.98))

    plot_html = fig.to_html(full_html=False, default_width="100%", default_height="700px")

    return HTMLResponse(
        f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ResearchOS Dashboard</title>
        <meta charset="utf-8" />
        <style>
            body {{ font-family: Arial, sans-serif; background: #1e1e1e; color: #eee; margin: 20px; }}
            h1 {{ color: #00d4ff; }}
            .status {{ background: #2a2a2a; padding: 10px; border-radius: 5px; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <h1>🚀 ResearchOS Live Dashboard</h1>
        <div id="plot">
            {plot_html}
        </div>
        <div class="status">
            <strong>📡 Live Updates:</strong> <span id="ws_data">Connecting...</span>
        </div>
        <script>
            var ws = new WebSocket('ws://localhost:8000/ws');
            ws.onopen = function() {{
                document.getElementById('ws_data').innerHTML = '✅ Connected. Waiting for updates...';
            }};
            ws.onmessage = function(e) {{
                document.getElementById('ws_data').innerHTML = e.data;
            }};
            ws.onclose = function() {{
                document.getElementById('ws_data').innerHTML = '❌ Disconnected';
            }};
        </script>
    </body>
    </html>
    """
    )


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(json.dumps({"time": str(datetime.now()), "status": "OK", "message": "ResearchOS is running"}))
            await asyncio.sleep(2)
    except Exception:
        pass
