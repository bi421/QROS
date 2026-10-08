import glob
import sys

import pandas as pd

sys.path.insert(0, ".")
from researchos.engines.ml.features import create_features
from researchos.engines.ml.model import train_model
from researchos.engines.ml.strategy import MLStrategy
from researchos.quant_engine.backtest import BacktestEngine

print("Loading data...")
files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
df = pd.concat(
    [pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files],
    ignore_index=True,
)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")

# 4h resample
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()

# цагийн шинж нэмэх
df_h["hour"] = df_h.index.hour
df_h["dayofweek"] = df_h.index.dayofweek
df_h["month"] = df_h.index.month

print(f"Data loaded: {len(df_h)} bars (4h)")

# Train/val/test split
dates = df_h.index
split1 = int(len(dates) * 0.7)
split2 = int(len(dates) * 0.85)
train_df = df_h.iloc[:split1]
val_df = df_h.iloc[split1:split2]
test_df = df_h.iloc[split2:]

# Feature generation (create_features-г өөрчлөх шаардлагатай, эсвэл шинэ функц бичих)
# Энд create_features нь зөвхөн close дээр ажилладаг, харин бид hour/dayofweek нэмсэн.
# Тиймээс би энгийнээр стандарт create_features-г ашиглаад дараа нь шинжүүдийг нэмнэ.


def prepare_features(df):
    df_feat = create_features(df)
    if df_feat.empty:
        return None
    # Цагийн шинжүүдийг нэмэх
    df_feat["hour"] = df["hour"]
    df_feat["dayofweek"] = df["dayofweek"]
    df_feat["month"] = df["month"]
    return df_feat


train_feat = prepare_features(train_df)
val_feat = prepare_features(val_df)
test_feat = prepare_features(test_df)

# XGBoost модел сургах
model, scaler, metrics = train_model(
    train_feat,
    model_type="xgboost",
    test_size=0.0,  # Validation-д тусад нь хадгалсан
)
print(f"Model accuracy: {metrics['test_accuracy']:.2%}")

# Grid search on validation
thresholds = [0.45, 0.48, 0.50, 0.52, 0.55, 0.58]
engine = BacktestEngine()
best_sharpe = -999
best_th = 0.55

for th in thresholds:
    strategy = MLStrategy(model, scaler, metrics["feature_names"], threshold=th)
    val_prices = val_df["close"].tolist()
    result = engine.run(val_prices, strategy)
    if result.num_trades >= 30 and result.sharpe_ratio > best_sharpe:
        best_sharpe = result.sharpe_ratio
        best_th = th

print(f"Best threshold (validation): {best_th}")

# Test
strategy_final = MLStrategy(model, scaler, metrics["feature_names"], threshold=best_th)
test_prices = test_df["close"].tolist()
test_result = engine.run(test_prices, strategy_final)

print("\n=== OUT-OF-SAMPLE TEST ===")
print(f"Trades: {test_result.num_trades}")
print(f"Return: {test_result.total_return:.2%}")
print(f"Sharpe: {test_result.sharpe_ratio:.2f}")
print(f"Max DD: {test_result.max_drawdown:.2%}")
print(f"Win Rate: {test_result.win_rate:.2%}")
