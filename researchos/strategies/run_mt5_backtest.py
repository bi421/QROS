import sys

sys.path.insert(0, ".")
from datetime import datetime, timedelta

from researchos.data_engine.broker_connectors import MT5Connector
from researchos.quant_engine.vectorized_backtest import vectorized_backtest

print("=" * 60)
print("📈 SMA20/100 STRATEGY BACKTEST (MT5 DATA)")
print("=" * 60)

connector = MT5Connector()
if not connector.is_available():
    print("❌ MT5 not available.")
    sys.exit(1)

# 1. Өгөгдөл татах (сүүлийн 2 жил)
symbol = "XAUUSD"
timeframe = "4h"
n_bars = 2000  # ~ 2000 * 4h = 8000h ≈ 333 days
end = datetime.now()
start = end - timedelta(days=400)  # enough to get 2000 bars

print(f"\n📊 Fetching {n_bars} bars of {symbol} {timeframe}...")
df = connector.fetch_recent(symbol, timeframe, n_bars)

if df.empty:
    print("❌ No data fetched.")
    sys.exit(1)

print(f"✅ Fetched {len(df)} bars")
print(f"📅 {df.index.min()} -> {df.index.max()}")

# 2. SMA20/100
close = df["close"]
sma20 = close.rolling(20).mean()
sma100 = close.rolling(100).mean()

signals = []
for i in range(100, len(df)):
    if sma20.iloc[i] > sma100.iloc[i] and sma20.iloc[i - 1] <= sma100.iloc[i - 1]:
        signals.append(("BUY", close.iloc[i]))
    elif sma20.iloc[i] < sma100.iloc[i] and sma20.iloc[i - 1] >= sma100.iloc[i - 1]:
        signals.append(("SELL", close.iloc[i]))

print(f"📊 Generated {len(signals)} signals")

if signals:
    result = vectorized_backtest(close.tolist(), signals)
    print("\n📊 BACKTEST RESULTS (MT5 data)")
    print(f"Trades: {result['num_trades']}")
    print(f"Return: {result['total_return']:.2%}")
    print(f"Sharpe: {result['sharpe']:.2f}")
    print(f"Max DD: {result['max_drawdown']:.2%}")
    print(f"Win Rate: {result['win_rate']:.2%}")
else:
    print("❌ No signals generated.")
