import sys
import time

sys.path.insert(0, ".")
from researchos.brokers.mt5_broker import MT5Broker

print("=" * 60)
print("🚀 RESEARCHOS LIVE TRADING (MT5)")
print("=" * 60)

# ===== CONFIGURATION =====
SYMBOL = "XAUUSD"
TIMEFRAME = "4h"
RISK_PERCENT = 0.02  # 2% risk per trade
SL_POINTS = 200  # Stop Loss points
RR_RATIO = 2.0  # Risk/Reward ratio (2:1 => TP = 400 points)
POSITION_COMMENT = "SMA20_100"
# =========================

try:
    broker = MT5Broker(symbol=SYMBOL, magic=123456)
except Exception as e:
    print(f"❌ Failed to connect MT5: {e}")
    sys.exit(1)

# 1. Get latest data
print(f"\n📊 Fetching last 300 bars of {SYMBOL} {TIMEFRAME}...")
df = broker.get_last_bars(TIMEFRAME, count=300)
if df.empty:
    print("❌ No data fetched.")
    broker.shutdown()
    sys.exit(1)

print(f"   Data range: {df.index.min()} -> {df.index.max()}")

# 2. Calculate SMA20/100
close = df["close"]
sma20 = close.rolling(20).mean()
sma100 = close.rolling(100).mean()

# 3. Check crossover on the last 2 bars
last_sma20 = sma20.iloc[-1]
last_sma100 = sma100.iloc[-1]
prev_sma20 = sma20.iloc[-2]
prev_sma100 = sma100.iloc[-2]

signal = None
if last_sma20 > last_sma100 and prev_sma20 <= prev_sma100:
    signal = "BUY"
elif last_sma20 < last_sma100 and prev_sma20 >= prev_sma100:
    signal = "SELL"

if signal is None:
    print(f"\n⏳ No signal. SMA20={last_sma20:.2f}, SMA100={last_sma100:.2f}")
    broker.shutdown()
    sys.exit(0)

print(f"\n📊 Signal detected: {signal}")

# 4. Get account balance and calculate lot size
acc_info = broker.get_account_info()
balance = acc_info.get("balance", 10000)
print("💰 Account Balance: ")

lot_size = broker.calculate_lot_size(risk_percent=RISK_PERCENT, stop_loss_points=SL_POINTS, account_balance=balance)
print(f"📐 Lot size: {lot_size:.2f} (0.01 = 1$ per point)")

# 5. Check existing positions
positions = broker.get_positions()
if not positions.empty:
    print(f"📋 Existing positions: {len(positions)}")
    # Close existing positions first if opposite signal
    for _, pos in positions.iterrows():
        if (signal == "BUY" and pos["type"] == "SELL") or (signal == "SELL" and pos["type"] == "BUY"):
            print(f"   Closing opposite position: Ticket {pos['ticket']}")
            broker.close_position(pos["ticket"])
            time.sleep(1)
    # If already have same direction, skip
    if any(pos["type"] == signal for _, pos in positions.iterrows()):
        print(f"✅ Already in {signal} position. Skipping.")
        broker.shutdown()
        sys.exit(0)

# 6. Place order
bid, ask = broker.get_current_price()
entry_price = ask if signal == "BUY" else bid
print(f"💰 Current price: {entry_price:.2f} (BID={bid:.2f}, ASK={ask:.2f})")

if signal == "BUY":
    sl_price = entry_price - SL_POINTS * 0.1
    tp_price = entry_price + SL_POINTS * 0.1 * RR_RATIO
else:
    sl_price = entry_price + SL_POINTS * 0.1
    tp_price = entry_price - SL_POINTS * 0.1 * RR_RATIO

print(f"   🛑 Stop Loss: {sl_price:.2f} ({SL_POINTS} pts)")
print(f"   🎯 Take Profit: {tp_price:.2f} ({int(SL_POINTS * RR_RATIO)} pts)")

print(f"\n⏳ Placing {signal} order...")
result = broker.place_order(
    action=signal,
    volume=lot_size,
    sl_price=sl_price,
    tp_price=tp_price,
    comment=f"{POSITION_COMMENT}_{signal}",
)

if "error" in result:
    print(f"❌ Order failed: {result['error']}")
else:
    print(f"✅ Order placed! Ticket: {result['ticket']} @ {result['price']:.2f}")

print("\n📋 Final Positions:")
print(broker.get_positions())

broker.shutdown()
print("\n🔌 Done.")
