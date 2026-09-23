import sys  # noqa: E402
import warnings  # noqa: E402

warnings.filterwarnings("ignore")
sys.path.insert(0, "cpp_quant")

import glob  # noqa: E402
import time  # noqa: E402

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from cpp_quant import run_ml_backtest_cpp  # noqa: E402
from joblib import Parallel, delayed  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from tensorflow.keras.callbacks import EarlyStopping  # noqa: E402
from tensorflow.keras.layers import LSTM, Dense, Dropout  # noqa: E402
from tensorflow.keras.models import Sequential  # noqa: E402

print("=" * 60)
print("🧠 LSTM DEEP LEARNING – XAUUSD 4h")
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
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
print(f"Data: {len(df_h)} bars (4h)")


# =============================================
# 2. FEATURES
# =============================================
def make_features(df):
    df = df.copy()
    close = df["close"]
    df["ret1"] = close.pct_change()
    for lag in [1, 2, 3, 5, 10, 20]:
        df[f"ret_lag_{lag}"] = df["ret1"].shift(lag)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    exp1, exp2 = close.ewm(span=12).mean(), close.ewm(span=26).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_diff"] = df["macd"] - df["macd_signal"]
    mean, std = close.rolling(20).mean(), close.rolling(20).std()
    df["bb_pos"] = (close - mean + 2 * std) / (4 * std)
    df["volatility"] = df["ret1"].rolling(20).std()
    df["target"] = (close.shift(-1) > close).astype(int)
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    return df


df_feat = make_features(df_h)
feature_cols = [c for c in df_feat.columns if c != "target"]
X = df_feat[feature_cols].values
y = df_feat["target"].values

# =============================================
# 3. TRAIN/VAL/TEST SPLIT
# =============================================
train_mask = df_h.index.year <= 2023
val_mask = df_h.index.year == 2024
test_mask = df_h.index.year >= 2025

X_train, y_train = X[train_mask], y[train_mask]
X_val, y_val = X[val_mask], y[val_mask]
X_test, y_test = X[test_mask], y[test_mask]

print(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

# =============================================
# 4. LSTM DATA PREPARATION (lookback=60)
# =============================================
LOOKBACK = 60


def create_sequences(X, y, lookback):
    X_seq, y_seq = [], []
    for i in range(lookback, len(X)):
        X_seq.append(X[i - lookback : i])
        y_seq.append(y[i])
    return np.array(X_seq), np.array(y_seq)


# Scale features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)
X_test_scaled = scaler.transform(X_test)

# Create sequences
X_train_seq, y_train_seq = create_sequences(X_train_scaled, y_train, LOOKBACK)
X_val_seq, y_val_seq = create_sequences(X_val_scaled, y_val, LOOKBACK)
X_test_seq, y_test_seq = create_sequences(X_test_scaled, y_test, LOOKBACK)

print(f"Train sequences: {len(X_train_seq)}, Val: {len(X_val_seq)}, Test: {len(X_test_seq)}")

# =============================================
# 5. BUILD LSTM MODEL
# =============================================
model = Sequential(
    [
        LSTM(64, return_sequences=True, input_shape=(LOOKBACK, X_train_seq.shape[2])),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(1, activation="sigmoid"),
    ]
)

model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
model.summary()

# =============================================
# 6. TRAIN
# =============================================
es = EarlyStopping(patience=10, restore_best_weights=True, monitor="val_loss")
print("\n🔥 Training LSTM...")
start = time.time()
history = model.fit(
    X_train_seq,
    y_train_seq,
    validation_data=(X_val_seq, y_val_seq),
    epochs=50,
    batch_size=32,
    callbacks=[es],
    verbose=1,
)
print(f"Training time: {time.time() - start:.2f}s")

# =============================================
# 7. EVALUATE
# =============================================
train_acc = model.evaluate(X_train_seq, y_train_seq, verbose=0)[1]
val_acc = model.evaluate(X_val_seq, y_val_seq, verbose=0)[1]
test_acc = model.evaluate(X_test_seq, y_test_seq, verbose=0)[1]
print(f"Train accuracy: {train_acc:.2%}, Val accuracy: {val_acc:.2%}, Test accuracy: {test_acc:.2%}")

# =============================================
# 8. SIGNALS & BACKTEST (C++)
# =============================================
# Predict probabilities on validation and test
val_probs = model.predict(X_val_seq, verbose=0).flatten()
test_probs = model.predict(X_test_seq, verbose=0).flatten()

# Map back to original indices (skip first LOOKBACK)
val_prices = df_h["close"].values[val_mask][LOOKBACK:].tolist()
test_prices = df_h["close"].values[test_mask][LOOKBACK:].tolist()

thresholds = [0.48, 0.50, 0.52, 0.55, 0.58]


def eval_th(th):
    signals = []
    for i, prob in enumerate(val_probs):
        price = val_prices[i]
        if prob > th:
            signals.append(("BUY", price))
        elif prob < (1 - th):
            signals.append(("SELL", price))
    if not signals:
        return th, {"trades": 0, "sharpe": -999}
    actions, prices = zip(*signals)
    res = run_ml_backtest_cpp(val_prices, val_probs.tolist(), th)
    return th, {"trades": res[4], "sharpe": res[1], "return": res[0], "dd": res[2], "wr": res[3]}


print("\n🔍 Grid search (C++ turbo)")
print("Threshold | Trades | Return  | Sharpe | MaxDD  | WinRate")
print("----------|--------|---------|--------|--------|--------")
results = Parallel(n_jobs=-1, prefer="threads")(delayed(eval_th)(th) for th in thresholds)
best_sharpe, best_th = -999, 0.52
for th, res in results:
    if res["trades"] >= 15 and res["sharpe"] > best_sharpe:
        best_sharpe, best_th = res["sharpe"], th
    print(f"{th:5.2f}     | {res['trades']:6d} | {res['return']:7.2%} | {res['sharpe']:6.2f} | {res['dd']:6.2%} | {res['wr']:7.2%}")
print(f"Best: {best_th} (Sharpe={best_sharpe:.2f})")

# Test
test_signals = []
for i, prob in enumerate(test_probs):
    price = test_prices[i]
    if prob > best_th:
        test_signals.append(("BUY", price))
    elif prob < (1 - best_th):
        test_signals.append(("SELL", price))
res_test = run_ml_backtest_cpp(test_prices, test_probs.tolist(), best_th)

print("\n📊 OUT-OF-SAMPLE TEST (2025-2026)")
print(f"Trades: {res_test[4]}")
print(f"Return: {res_test[0]:.2%}")
print(f"Sharpe: {res_test[1]:.2f}")
print(f"Max DD: {res_test[2]:.2%}")
print(f"Win Rate: {res_test[3]:.2%}")

status = "✅ SUCCESS" if res_test[4] >= 30 and res_test[1] > 0.5 else "❌ FAILED"
print(status)

# Save model
model.save("lstm_xauusd_4h.keras")
joblib.dump(scaler, "lstm_scaler.pkl")
print("💾 Model saved: lstm_xauusd_4h.keras")
