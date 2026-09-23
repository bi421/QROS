import sys  # noqa: E402

# noqa: E402
import warnings  # noqa: E402

# noqa: E402

warnings.filterwarnings("ignore")
sys.path.insert(0, "cpp_quant")

import glob  # noqa: E402

# noqa: E402
import numpy as np  # noqa: E402

# noqa: E402
import pandas as pd  # noqa: E402

# noqa: E402
from cpp_quant import run_ml_backtest_cpp  # noqa: E402

# noqa: E402
from joblib import Parallel, delayed  # noqa: E402

# noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

# noqa: E402
from xgboost import XGBClassifier  # хэрэв regression бол XGBRegressor  # noqa: E402

# noqa: E402

print("=" * 60)
print("🚀 SHINEE FEATURE-UD: XAUUSD 4h")
print("=" * 60)

# =============================================
# 1. ӨГӨГДӨЛ АЧААЛАХ
# =============================================
print("Loading XAUUSD data...")
files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
df = pd.concat(
    [pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files],
    ignore_index=True,
)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
print(f"Data: {len(df_h)} bars (4h)")


# =============================================
# 2. FEATURE GENERATION (ШИНЭЧИЛСЭН)
# =============================================
def add_new_features(df):
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"] if "volume" in df.columns else None

    # ЦАГИЙН ЦИКЛ (4h тул 6 интервал)
    hour = df.index.hour
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dayofweek_sin"] = np.sin(2 * np.pi * df.index.dayofweek / 7)
    df["dayofweek_cos"] = np.cos(2 * np.pi * df.index.dayofweek / 7)

    # 24 ЦАГИЙН ХАМГИЙН ИХ/БАГА
    rolling_high = high.rolling(6).max()  # 4h * 6 = 24h
    rolling_low = low.rolling(6).min()
    df["price_vs_high_24h"] = close / rolling_high - 1
    df["price_vs_low_24h"] = close / rolling_low - 1

    # ATR (14) / close – волатилийн харьцаа
    tr = np.maximum(high - low, np.maximum((high - close.shift()).abs(), (low - close.shift()).abs()))
    atr = tr.rolling(14).mean()
    df["atr_ratio"] = atr / close

    # ADX (трендийн хүч) – аль хэдийн features.py-д байсан ч энд шууд хийе
    # Энгийн ADX (14) – бүрэн код биш, гэхдээ бид аль хэдийн create_features-д байгаа
    # Энд бид өмнөх ADX-г ашиглахгүй, шинээр тооцоолсон нэмнэ
    # (хялбарчилсан: RSI-тэй төстэй, гэхдээ нарийн код биш)
    # Бид одоо бусад feature-д анхаарна.

    # VOLUME RATIO (хэрэв volume байгаа бол)
    if volume is not None:
        df["volume_ma5"] = volume.rolling(5).mean()
        df["volume_ratio"] = volume / df["volume_ma5"]
        df.drop("volume_ma5", axis=1, inplace=True)

    # ӨМНӨХ FEATURE-ҮҮД (өгөөж, lag, RSI, MACD, BB, volatility) – хадгал
    df["ret1"] = close.pct_change()
    for lag in [1, 2, 3, 5, 10, 20]:
        df[f"ret_lag_{lag}"] = df["ret1"].shift(lag)
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    # MACD
    exp1 = close.ewm(span=12).mean()
    exp2 = close.ewm(span=26).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_diff"] = df["macd"] - df["macd_signal"]
    # Bollinger
    mean = close.rolling(20).mean()
    std = close.rolling(20).std()
    df["bb_pos"] = (close - mean + 2 * std) / (4 * std)
    df["volatility"] = df["ret1"].rolling(20).std()

    # TARGET (1/0 classification) – хэрэв regression хүсвэл target-г өөрчлөх
    df["target"] = (close.shift(-1) > close).astype(int)

    # NaN-г арилгах
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    return df


df_h = add_new_features(df_h)

# =============================================
# 3. TRAIN/VAL/TEST SPLIT
# =============================================
train_mask = df_h.index.year <= 2023
val_mask = df_h.index.year == 2024
test_mask = df_h.index.year >= 2025

train_df = df_h[train_mask]
val_df = df_h[val_mask]
test_df = df_h[test_mask]
print(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

feature_cols = [c for c in train_df.columns if c not in ["target", "volume"]]
X_train = train_df[feature_cols].values
y_train = train_df["target"].values
X_val = val_df[feature_cols].values
y_val = val_df["target"].values
X_test = test_df[feature_cols].values
y_test = test_df["target"].values

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_val_s = scaler.transform(X_val)
X_test_s = scaler.transform(X_test)

# =============================================
# 4. MODEL (XGBoost classification)
# =============================================
model = XGBClassifier(
    n_estimators=100,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    use_label_encoder=False,
    eval_metric="logloss",
)
model.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)
print(f"Train acc: {model.score(X_train_s, y_train):.2%}, Val acc: {model.score(X_val_s, y_val):.2%}")

# =============================================
# 5. GRID SEARCH (C++ backtest)
# =============================================
thresholds = [0.50, 0.52, 0.55, 0.58, 0.60]


def eval_th(th):
    val_probs = model.predict_proba(X_val_s)[:, 1]
    val_prices = val_df["close"].values.tolist()
    res = run_ml_backtest_cpp(val_prices, val_probs.tolist(), th)
    return th, {"trades": res[4], "sharpe": res[1], "return": res[0], "dd": res[2], "wr": res[3]}


print("\n🔍 Validation grid search (C++ turbo)")
print("Threshold | Trades | Return  | Sharpe | MaxDD  | WinRate")
print("----------|--------|---------|--------|--------|--------")
results = Parallel(n_jobs=-1, prefer="threads")(delayed(eval_th)(th) for th in thresholds)
best_sharpe, best_th = -999, 0.55
for th, res in results:
    if res["trades"] >= 15 and res["sharpe"] > best_sharpe:
        best_sharpe, best_th = res["sharpe"], th
    print(f"{th:5.2f}     | {res['trades']:6d} | {res['return']:7.2%} | {res['sharpe']:6.2f} | {res['dd']:6.2%} | {res['wr']:7.2%}")
print(f"Best: {best_th} (Sharpe={best_sharpe:.2f})")

# =============================================
# 6. TEST
# =============================================
test_probs = model.predict_proba(X_test_s)[:, 1]
test_prices = test_df["close"].values.tolist()
res_test = run_ml_backtest_cpp(test_prices, test_probs.tolist(), best_th)

print("\n📊 OUT-OF-SAMPLE TEST (2025-2026)")
print(f"Trades: {res_test[4]}")
print(f"Return: {res_test[0]:.2%}")
print(f"Sharpe: {res_test[1]:.2f}")
print(f"Max DD: {res_test[2]:.2%}")
print(f"Win Rate: {res_test[3]:.2%}")

status = "✅ SUCCESS" if res_test[4] >= 30 and res_test[1] > 0.5 else "❌ FAILED"
print(status)
