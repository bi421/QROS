import sys

sys.path.insert(0, ".")
from datetime import datetime, timedelta

from researchos.data_engine.broker_connectors import MT5Connector

print("=" * 60)
print("🔌 MT5 CONNECTOR TEST")
print("=" * 60)

connector = MT5Connector()

if connector.is_available():
    symbol = "XAUUSD"
    tf = "1h"
    n_bars = 100
    end = datetime.now()
    start = end - timedelta(days=30)

    print(f"\n📊 Fetching {n_bars} bars of {symbol} {tf}...")
    df = connector.fetch_recent(symbol, tf, n_bars)

    if not df.empty:
        print(f"✅ Fetched {len(df)} bars")
        print(f"📅 {df.index.min()} -> {df.index.max()}")
        print("\n📋 Last 5 rows:")
        print(df.tail())
    else:
        print("❌ No data fetched. Check symbol and MT5 connection.")
else:
    print("❌ MT5 not available. Ensure MetaTrader 5 is running.")
