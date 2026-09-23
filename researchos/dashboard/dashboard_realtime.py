import asyncio
import random
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cpp_quant_engine" / "python"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

app = FastAPI(title="ResearchOS Real-time Dashboard")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ResearchOS Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #333; }
        button { padding: 12px 24px; font-size: 16px; background: #4CAF50; color: white; border: none; cursor: pointer; border-radius: 4px; }
        button:hover { background: #45a049; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; background: white; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background: #4CAF50; color: white; }
        tr:nth-child(even) { background: #f2f2f2; }
        .status { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .status-ok { background: #d4edda; color: #155724; }
        .status-err { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ResearchOS Quant Engine Dashboard</h1>
        <div id="status" class="status status-ok">WebSocket холбогдож байна...</div>
        <button onclick="runGridSearch()">Grid Search Ажиллуулах</button>
        <div id="results"></div>
    </div>
    <script>
        let ws;
        function connect() {
            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            ws = new WebSocket(protocol + "//" + window.location.host + "/ws/grid-search");
            ws.onopen = function() {
                document.getElementById("status").textContent = "✅ WebSocket холбогдлоо!";
                document.getElementById("status").className = "status status-ok";
            };
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                if (data.status === "started") {
                    document.getElementById("results").innerHTML = "<p>Өгөгдөл ачаалагдаж байна...</p>";
                } else if (data.status === "completed") {
                    displayResults(data.results);
                } else if (data.status === "error") {
                    document.getElementById("results").innerHTML = "<p style='color:red'>Алдаа: " + data.message + "</p>";
                }
            };
            ws.onclose = function() {
                document.getElementById("status").textContent = "❌ WebSocket саллаа. 3 секундын дараа дахин холбогдоно...";
                document.getElementById("status").className = "status status-err";
                setTimeout(connect, 3000);
            };
            ws.onerror = function(err) {
                console.error("WebSocket error:", err);
            };
        }
        function runGridSearch() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({"action": "run"}));
            } else {
                alert("WebSocket холбогдоогүй байна!");
            }
        }
        function displayResults(results) {
            let html = "<h2>Grid Search Үр Дүн (" + results.length + ")</h2>";
            html += "<table><tr><th>MA Period</th><th>RSI Threshold</th><th>Sharpe Ratio</th><th>Max Drawdown</th><th>Total Return</th></tr>";
            results.forEach(function(r) {
                html += "<tr><td>" + r.ma_period + "</td><td>" + r.rsi_threshold + "</td><td>" + r.sharpe_ratio + "</td><td>" + r.max_drawdown + "</td><td>" + r.total_return + "</td></tr>";
            });
            html += "</table>";
            document.getElementById("results").innerHTML = html;
        }
        connect();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


@app.websocket("/ws/grid-search")
async def websocket_grid_search(websocket: WebSocket):
    await websocket.accept()
    print("🔌 WebSocket холбогдлоо")
    try:
        while True:
            data = await websocket.receive_json()
            print(f"📥 Мессеж хүлээж авлаа: {data}")

            # Mock үр дүн үүсгэх
            results = []
            for ma in [10, 20, 50]:
                for rsi in [30, 50, 70]:
                    results.append({"ma_period": ma, "rsi_threshold": rsi, "sharpe_ratio": round(random.uniform(1.5, 2.5), 3), "max_drawdown": round(random.uniform(0.05, 0.15), 3), "total_return": round(random.uniform(0.20, 0.40), 3)})

            print(f"✅ {len(results)} үр дүн бэлэн. Илгээж байна...")

            await websocket.send_json({"status": "started", "message": "Grid search эхэлж байна..."})
            await asyncio.sleep(0.5)

            await websocket.send_json({"status": "completed", "results": results, "best_params": results[0], "count": len(results)})
            print("📤 Үр дүн илгээгдлээ!")

    except Exception as e:
        print(f"❌ Алдаа: {e}")
        import traceback

        traceback.print_exc()
    finally:
        print("🔌 WebSocket хаагдлаа")


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print(" ResearchOS Dashboard Server")
    print("=" * 60)
    print("🌐 URL: http://127.0.0.1:8000")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8000)
