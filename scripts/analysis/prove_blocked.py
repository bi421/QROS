import json
import sys
from pathlib import Path

from researchos.data_engine.loader import CsvLoader
from researchos.experiments.phase51 import Phase51Config, run_phase51

csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/curated/xauusd/xauusd_d1_2023_2025_from_m1.csv")
print(f"=== PROVING BLOCKED-GUARD WITH CSV: {csv_path} ===")
loader = CsvLoader()
try:
    candles = loader.load_mt5_candles(str(csv_path), symbol="XAUUSD", timeframe="1d")
except Exception as e:
    # try generic loader
    print(f"MT5 loader failed: {e}, trying load_csv")
    candles = loader.load_csv(str(csv_path))

print(f"Loaded candles: {len(candles)} - Required >=2000")
if len(candles) < 2000:
    print(f"BLOCKED CORRECTLY: {len(candles)} < 2000 -> Phase51Config will block")
else:
    print(f"Enough bars: {len(candles)}")

close = [c.close for c in candles]
high = [c.high for c in candles]
low = [c.low for c in candles]
volume = [getattr(c, "volume", 0) or getattr(c, "tick_volume", 0) for c in candles]

cfg = Phase51Config(
    symbol="XAUUSD",
    timeframe="1d",
    horizon=5,
    threshold=0.0,
    train_size=1000,
    validation_size=150,
    step_size=150,
    estimator_feature=0,
    spread_spec="fixed:0.20",
    slippage_spec="fixed:0.10",
    commission_spec="fixed:0.05",
)

res = run_phase51(close, high, low, volume, cfg)
print(json.dumps(res.to_dict() if hasattr(res, "to_dict") else res.__dict__, indent=2, default=str))
