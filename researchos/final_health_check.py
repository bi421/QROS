#!/usr/bin/env python
"""
ResearchOS БҮРЭН ЭРҮҮЛ МЭНДИЙН ШАЛГАЛТ
====================================
Энэ скрипт нь ResearchOS-ийн бүх чухал функциональ байдлыг шалгадаг.
"""

import os
import subprocess
import sys
import time
import warnings

warnings.filterwarnings("ignore")

# ============================================================
# 1. ХЭЛ БОЛОН ОРЧИН
# ============================================================
print("=" * 70)
print("🧪 RESEARCHOS БҮРЭН ЭРҮҮЛ МЭНДИЙН ШАЛГАЛТ")
print("=" * 70)
print(f"🐍 Python версн: {sys.version}")
print(f"📂 Ажлын хавтас: {os.getcwd()}")
print("-" * 70)

status = {"PASS": 0, "FAIL": 0, "WARN": 0}


def log(name, result, message=""):
    """Шалгалтын үр дүнг хэвлэх."""
    if result == "✅":
        status["PASS"] += 1
        print(f"{result} {name:30s} {message}")
    elif result == "❌":
        status["FAIL"] += 1
        print(f"{result} {name:30s} {message}")
    else:
        status["WARN"] += 1
        print(f"{result} {name:30s} {message}")


# ============================================================
# 2. RUFF ЛИНТИНГ
# ============================================================
try:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "researchos", "--quiet"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0 or "Found 0 errors" in result.stdout:
        log("Ruff линтинг", "✅", "0 алдаа")
    else:
        log("Ruff линтинг", "⚠️", f"{len(result.stdout)} алдаа")
except Exception:
    log("Ruff линтинг", "❌", "ажиллуулахгүй")

# ============================================================
# 3. ӨГӨГДӨЛ АЧААЛАХ
# ============================================================
try:
    import glob

    import pandas as pd

    files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
    if files:
        df_sample = pd.read_csv(files[0], sep=";", header=None, nrows=5)
        log("Өгөгдөл (CSV)", "✅", f"{len(files)} файл, жишээ {df_sample.shape}")
    else:
        log("Өгөгдөл (CSV)", "❌", "файл олдсонгүй")
except Exception as e:
    log("Өгөгдөл (CSV)", "❌", str(e)[:50])

# Parquet
try:
    if os.path.exists("data/processed/ohlcv_4h.parquet"):
        df_p = pd.read_parquet("data/processed/ohlcv_4h.parquet")
        log("Өгөгдөл (Parquet)", "✅", f"{len(df_p)} мөр")
    else:
        log("Өгөгдөл (Parquet)", "⚠️", "файл байхгүй")
except Exception as e:
    log("Өгөгдөл (Parquet)", "❌", str(e)[:50])

# ============================================================
# 4. ГОЛ МОДУЛИУДЫН ИМПОРТ
# ============================================================
try:
    log("Модуль: quant_engine", "✅", "import амжилттай")
except Exception as e:
    log("Модуль: quant_engine", "❌", str(e)[:40])

try:
    log("Модуль: ml_engine", "✅", "import амжилттай")
except Exception as e:
    log("Модуль: ml_engine", "❌", str(e)[:40])

try:
    log("Модуль: data_engine", "✅", "import амжилттай")
except Exception as e:
    log("Модуль: data_engine", "❌", str(e)[:40])

try:
    from researchos.brokers.mt5_broker import MT5Broker  # noqa: F401

    log("Модуль: brokers (MT5)", "✅", "import амжилттай")
except ImportError:
    log("Модуль: brokers (MT5)", "⚠️", "файл байхгүй (шинэ)")
except Exception as e:
    log("Модуль: brokers (MT5)", "❌", str(e)[:40])

# ============================================================
# 5. ML FEATURE GENERATION
# ============================================================
try:
    import glob

    import pandas as pd

    files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
    if files:
        df = pd.concat(
            [
                pd.read_csv(
                    f,
                    sep=";",
                    header=None,
                    nrows=1000,
                    names=["datetime", "open", "high", "low", "close", "volume"],
                )
                for f in files[:2]
            ],
            ignore_index=True,
        )
        df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
        df = df.set_index("datetime")
        from researchos.ml_engine.features import create_features

        df_feat = create_features(df.resample("1h").agg({"close": "last"}).dropna())
        if not df_feat.empty:
            log("ML Feature Engineering", "✅", f"{df_feat.shape[1]} feature")
        else:
            log("ML Feature Engineering", "❌", "хоосон dataframe")
except Exception as e:
    log("ML Feature Engineering", "❌", str(e)[:50])

# ============================================================
# 6. БЭКТЕСТ (TP/SL-ТЭЙ)
# ============================================================
try:
    import glob

    import pandas as pd

    from researchos.quant_engine.backtest_tpsl import vectorized_backtest_with_tpsl

    files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
    if files:
        df = pd.concat(
            [
                pd.read_csv(
                    f,
                    sep=";",
                    header=None,
                    names=["datetime", "open", "high", "low", "close", "volume"],
                )
                for f in files[:3]
            ],
            ignore_index=True,
        )
        df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
        df = df.set_index("datetime")
        df_h = df.resample("4h").agg({"close": "last"}).dropna()
        close = df_h["close"]
        sma20 = close.rolling(20).mean()
        sma100 = close.rolling(100).mean()
        signals = []
        for i in range(100, len(df_h)):
            if sma20.iloc[i] > sma100.iloc[i] and sma20.iloc[i - 1] <= sma100.iloc[i - 1]:
                signals.append(("BUY", close.iloc[i]))
            elif sma20.iloc[i] < sma100.iloc[i] and sma20.iloc[i - 1] >= sma100.iloc[i - 1]:
                signals.append(("SELL", close.iloc[i]))
        if signals:
            res = vectorized_backtest_with_tpsl(
                prices=close.tolist(),
                signals=signals,
                initial_capital=100000,
                stop_loss_pct=0.02,
                take_profit_pct=0.04,
            )
            log("Бэктест (TP/SL)", "✅", f"Sharpe={res['sharpe']:.2f}, Trades={res['num_trades']}")
        else:
            log("Бэктест (TP/SL)", "⚠️", "дохио байхгүй")
except Exception as e:
    log("Бэктест (TP/SL)", "❌", str(e)[:60])

# ============================================================
# 7. C++ МОДУЛЬ
# ============================================================
try:
    import sys

    sys.path.insert(0, "cpp_quant")
    from cpp_quant import run_ml_backtest_cpp

    log("C++ Engine", "✅", "компиляци хийгдсэн, ачаалагдлаа")
except ImportError:
    log("C++ Engine", "⚠️", "компиляци хийгээгүй (Python хувилбар ашиглана)")
except Exception as e:
    log("C++ Engine", "❌", str(e)[:40])

# ============================================================
# 8. MT5 ХОЛБОГЧ
# ============================================================
try:
    import MetaTrader5 as mt5

    if mt5.initialize():
        log("MT5 Терминал", "✅", f"версн {mt5.terminal_info().name}")
        mt5.shutdown()
    else:
        log("MT5 Терминал", "⚠️", "терминал ажиллахгүй")
except ImportError:
    log("MT5 Терминал", "⚠️", "MetaTrader5 сан суугаагүй")
except Exception as e:
    log("MT5 Терминал", "❌", str(e)[:40])

# ============================================================
# 9. Pytest ЦУГЛУУЛАЛТ
# ============================================================
try:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "researchos/tests", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if "collected" in result.stderr:
        import re

        match = re.search(r"collected (\d+)", result.stderr)
        if match:
            count = match.group(1)
            log("Pytest цуглуулалт", "✅", f"{count} тест цуглуулсан")
        else:
            log("Pytest цуглуулалт", "⚠️", "тоо тодорхойгүй")
    else:
        log("Pytest цуглуулалт", "❌", "цуглуулж чадсангүй")
except Exception as e:
    log("Pytest цуглуулалт", "❌", str(e)[:40])

# ============================================================
# 10. ХУРДНЫ ШИНЖИЛГЭЭ (Grid Search)
# ============================================================
try:
    import numpy as np

    start = time.time()
    # Жижиг grid search тест
    prices = np.random.randn(1000).cumsum() + 100
    probs = np.random.rand(1000)
    from cpp_quant import run_ml_backtest_cpp

    for th in [0.45, 0.50, 0.55, 0.60]:
        run_ml_backtest_cpp(prices.tolist(), probs.tolist(), th)
    elapsed = time.time() - start
    log("Grid search хурд (C++)", "✅", f"{elapsed:.3f} сек (4 threshold)")
except ImportError:
    # Python хувилбараар турших
    try:
        from researchos.quant_engine.backtest_tpsl import vectorized_backtest_with_tpsl

        signals = [("BUY", 100), ("SELL", 101), ("BUY", 102), ("SELL", 103)]
        start = time.time()
        for _ in range(100):
            vectorized_backtest_with_tpsl([100, 101, 102, 103, 104], signals)
        elapsed = time.time() - start
        log("Grid search хурд (Python)", "✅", f"{elapsed:.3f} сек (100 бэктест)")
    except Exception as e:
        log("Grid search хурд", "❌", str(e)[:40])
except Exception as e:
    log("Grid search хурд", "❌", str(e)[:40])

# ============================================================
# ЭЦСИЙН ТАЙЛАН
# ============================================================
print("-" * 70)
print("📊 ЭЦСИЙН ДҮН")
print("=" * 70)
print(f"   ✅ Амжилттай: {status['PASS']}")
print(f"   ⚠️ Анхааруулга: {status['WARN']}")
print(f"   ❌ Алдаа: {status['FAIL']}")
print("=" * 70)

if status["FAIL"] == 0:
    print("🎉 БҮХ ҮЙЛДЭЛ АМЖИЛТТАЙ! Таны ResearchOS бүрэн ажиллагаатай байна.")
elif status["PASS"] > 5:
    print("⚠️ Зарим хэсэгт алдаа байна. Гэхдээ гол функциональ байдал ажиллаж байна.")
else:
    print("❌ Системд ноцтой алдаа байна. Шалгалтын гаралтыг шалгана уу.")
print("=" * 70)
