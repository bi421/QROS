import sys

sys.path.insert(0, ".")
from datetime import datetime, timedelta

from researchos.data_engine import BrokerConnector, DataComparator

print("=" * 60)
print("🚀 DATA COMPARATOR: MT5 vs TradingView (tvdatafeed)")
print("=" * 60)

connector = BrokerConnector()
SYMBOL = "XAUUSD"
TIMEFRAME = "1h"
DAYS_BACK = 7

end = datetime.now()
start = end - timedelta(days=DAYS_BACK)

print(f"\n📌 Symbol: {SYMBOL}, Timeframe: {TIMEFRAME}, Period: {DAYS_BACK} days")
print("-" * 60)

print("📊 Fetching from MT5...")
df_mt5 = connector.fetch_mt5(SYMBOL, TIMEFRAME, start, end)
if not df_mt5.empty:
    print(f"   ✅ MT5 rows: {len(df_mt5)}")
    print(f"   📅 {df_mt5.index.min()} -> {df_mt5.index.max()}")
else:
    print("   ❌ No MT5 data. Ensure terminal is running and symbol is available.")

print("\n📊 Fetching from TradingView (tvdatafeed)...")
n_bars = 500
df_tv = connector.fetch_tradingview(SYMBOL, TIMEFRAME, n_bars=n_bars)
if not df_tv.empty:
    print(f"   ✅ TV rows: {len(df_tv)}")
    print(f"   📅 {df_tv.index.min()} -> {df_tv.index.max()}")
else:
    print("   ❌ No TV data. Check symbol/exchange or internet connection.")

if not df_mt5.empty and not df_tv.empty:
    print("\n🔍 Comparing data sources...")
    result = DataComparator.compare(df_mt5, df_tv, "MT5", "TradingView")
    print("\n📋 COMPARISON RESULTS:")
    print("=" * 60)
    for key, val in result.items():
        if isinstance(val, float):
            print(f"   {key:25s}: {val:.4f}")
        else:
            print(f"   {key:25s}: {val}")
    print("=" * 60)
    corr = result.get("correlation_close", 0)
    mape = result.get("mape_close_pct", 100)
    if corr > 0.99 and mape < 1.0:
        print("✅ DATA QUALITY: EXCELLENT (Correlation > 0.99, MAPE < 1%)")
    elif corr > 0.95 and mape < 5.0:
        print("⚠️ DATA QUALITY: GOOD (Minor discrepancies detected)")
    else:
        print("❌ DATA QUALITY: POOR (Check symbol mapping or timezone)")
else:
    print("\n❌ Cannot compare. One or both data sources are empty.")
    print("   💡 For MT5: Ensure MetaTrader 5 is installed and running, and symbol is added.")
    print("   💡 For TV: Check symbol name (e.g., 'XAUUSD' or 'GOLD').")
