from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# --- MT5 (PRIMARY) ---
try:
    import MetaTrader5 as mt5

    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    print("⚠️ MetaTrader5 module not installed. Run: pip install MetaTrader5")

# --- TradingView (SECONDARY / FUTURE COMPARISON) ---
TV_AVAILABLE = False
try:
    TV_AVAILABLE = True
except ImportError:
    pass
except Exception:
    pass

# --- yfinance (FALLBACK / FUTURE COMPARISON) ---
YF_AVAILABLE = False
try:
    YF_AVAILABLE = True
except ImportError:
    pass


class MT5Connector:
    """
    PRIMARY DATA SOURCE: MetaTrader 5.
    This connector is optimized for fetching reliable, broker-grade data.
    """

    TIMEFRAMES = {
        "1m": mt5.TIMEFRAME_M1 if MT5_AVAILABLE else None,
        "5m": mt5.TIMEFRAME_M5 if MT5_AVAILABLE else None,
        "15m": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else None,
        "30m": mt5.TIMEFRAME_M30 if MT5_AVAILABLE else None,
        "1h": mt5.TIMEFRAME_H1 if MT5_AVAILABLE else None,
        "4h": mt5.TIMEFRAME_H4 if MT5_AVAILABLE else None,
        "1d": mt5.TIMEFRAME_D1 if MT5_AVAILABLE else None,
    }

    def __init__(self) -> None:
        self.initialized = False
        if MT5_AVAILABLE:
            try:
                if not mt5.initialize():
                    print("⚠️ MT5 initialization failed. Is terminal running?")
                else:
                    self.initialized = True
                    print("✅ MT5 connected (primary data source).")
            except Exception as e:
                print(f"⚠️ MT5 init error: {e}")

    def is_available(self) -> bool:
        return bool(self.initialized)

    def fetch_ohlcv(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Fetch OHLCV data from MT5.

        Args:
            symbol: Trading symbol (e.g., 'XAUUSD', 'EURUSD')
            timeframe: '1m', '5m', '15m', '30m', '1h', '4h', '1d'
            start: datetime (UTC)
            end: datetime (UTC)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        if not self.initialized:
            raise ConnectionError("MT5 is not connected. Ensure terminal is running.")

        tf = self.TIMEFRAMES.get(timeframe)
        if tf is None:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        rates = mt5.copy_rates_range(symbol, tf, start, end)
        if rates is None or len(rates) == 0:
            print(f"⚠️ No MT5 data for {symbol} {timeframe}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(
            columns={
                "time": "datetime",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "tick_volume": "volume",
            }
        )
        df = df.set_index("datetime")[["open", "high", "low", "close", "volume"]]
        return df

    def fetch_recent(self, symbol: str, timeframe: str, n_bars: int = 1000) -> pd.DataFrame:
        """Fetch most recent n_bars of data from MT5."""
        end = datetime.now()
        # Estimate start time based on timeframe
        minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
        start = end - timedelta(minutes=minutes.get(timeframe, 60) * n_bars * 2)
        return self.fetch_ohlcv(symbol, timeframe, start, end)


class DataComparator:
    """
    FUTURE: Comparison module for validating MT5 data against other sources.
    This will be implemented later when needed.
    """

    @staticmethod
    def compare(
        df1: pd.DataFrame,
        df2: pd.DataFrame,
        source1: str = "MT5",
        source2: str = "Other",
    ) -> dict[str, object]:
        """
        Compare two OHLCV DataFrames.
        Returns correlation, MAPE, missing bars, etc.
        """
        if df1.empty or df2.empty:
            return {"error": "One or both DataFrames are empty."}

        # Ensure tz-naive for join
        for df in [df1, df2]:
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

        merged = df1.join(df2, lsuffix=f"_{source1}", rsuffix=f"_{source2}", how="outer")
        missing_s1 = merged[f"close_{source1}"].isna().sum()
        missing_s2 = merged[f"close_{source2}"].isna().sum()
        clean = merged.dropna(subset=[f"close_{source1}", f"close_{source2}"])

        if len(clean) == 0:
            return {"error": "No common timestamps found."}

        corr = clean[f"close_{source1}"].corr(clean[f"close_{source2}"])
        s1 = clean[f"close_{source1}"]
        s2 = clean[f"close_{source2}"]
        mape = np.mean(np.abs((s1 - s2) / s1)) * 100
        max_diff = (s1 - s2).abs().max()

        return {
            "source1": source1,
            "source2": source2,
            "total_bars_union": len(merged),
            "common_bars": len(clean),
            "missing_in_source1": missing_s1,
            "missing_in_source2": missing_s2,
            "correlation_close": corr,
            "mape_close_pct": mape,
            "max_close_diff": max_diff,
            "data_quality": "EXCELLENT" if corr > 0.99 and mape < 1.0 else "GOOD" if corr > 0.95 and mape < 5.0 else "POOR",
        }
