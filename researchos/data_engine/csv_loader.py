"""
CSV Loader — load market data from CSV files into Data Engine objects.

Based on Article XVII: Object Model — Data Layer.

The CSV Loader provides deterministic, auditable loading of market data
from CSV files. It supports candles, ticks, quotes, trades, and order
book data with configurable field mappings and timezone normalization.

Guarantees:
    - Deterministic: Same CSV → same objects (content-addressed IDs)
    - Reversible: Loaded data can be serialized back to CSV
    - Timezone-safe: All timestamps normalized to UTC
    - Error-tolerant: Configurable error handling (skip vs. fail)
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from typing import Any

from researchos.core.timestamp import _parse_iso_compat
from researchos.data_engine.candle import Candle
from researchos.data_engine.contracts import CandleField, LoaderConfig, Timeframe
from researchos.data_engine.quote import Quote
from researchos.data_engine.tick import Tick
from researchos.data_engine.timezone import normalize_timestamp
from researchos.data_engine.trade import Trade

FORMAT_GENERIC = "generic"
FORMAT_MT5 = "mt5"
FORMAT_TRADINGVIEW = "tradingview"


class CsvLoader:
    """
    Load market data from CSV files into Data Engine objects.

    Supports loading of:
        - OHLCV candles
        - Ticks
        - Quotes (bid/ask)
        - Trades

    Usage:
        loader = CsvLoader()
        candles = loader.load_candles("data.csv", symbol="XAU/USD", timeframe="1h")
    """

    def __init__(self, config: LoaderConfig | None = None):
        self.config = config or LoaderConfig()
        self._stats: dict[str, Any] = {
            "total_rows": 0,
            "loaded_rows": 0,
            "skipped_rows": 0,
            "error_rows": 0,
            "errors": [],
        }

    @property
    def stats(self) -> dict[str, Any]:
        """Get loading statistics."""
        return dict(self._stats)

    def load_candles(
        self,
        file_path: str,
        symbol: str,
        timeframe: str,
        field_mapping: CandleField | None = None,
    ) -> list[Candle]:
        """
        Load OHLCV candles from a CSV file.

        Args:
            file_path: Path to the CSV file.
            symbol: Symbol to assign to all candles.
            timeframe: Timeframe to assign to all candles.
            field_mapping: Optional custom field name mappings.

        Returns:
            List of Candle objects.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If required columns are missing.
        """
        mapping = field_mapping or self.config.field_mapping or CandleField()
        rows = self._read_csv(file_path)
        return self._parse_candles(rows, symbol, timeframe, mapping)

    def load_candles_from_text(
        self,
        text: str,
        symbol: str,
        timeframe: str,
        field_mapping: CandleField | None = None,
    ) -> list[Candle]:
        """
        Load OHLCV candles from a CSV string.

        Args:
            text: CSV content as a string.
            symbol: Symbol to assign to all candles.
            timeframe: Timeframe to assign to all candles.
            field_mapping: Optional custom field name mappings.

        Returns:
            List of Candle objects.
        """
        mapping = field_mapping or self.config.field_mapping or CandleField()
        rows = self._parse_csv_text(text)
        return self._parse_candles(rows, symbol, timeframe, mapping)

    def load_mt5_candles(
        self,
        file_path: str,
        symbol: str,
        timeframe: str | None = None,
        timezone: str | None = None,
    ) -> list[Candle]:
        """
        Load OHLCV candles from an MT5 exported CSV file.

        Handles the standard MT5 export layout where the date and time are
        split into separate columns (Date, Time, Open, High, Low, Close,
        Volume) as well as extended exports with tick_volume, real_volume,
        and spread columns.

        Args:
            file_path: Path to the MT5 CSV file.
            symbol: Symbol to assign to all candles.
            timeframe: Timeframe to assign (auto-detected if None).
            timezone: Source timezone (defaults to the loader config).

        Returns:
            List of Candle objects.
        """
        rows = self._read_csv(file_path)
        return self._parse_mt5_rows(rows, symbol, timeframe, timezone)

    def load_mt5_candles_from_text(
        self,
        text: str,
        symbol: str,
        timeframe: str | None = None,
        timezone: str | None = None,
    ) -> list[Candle]:
        """Load MT5 candles from a CSV string."""
        rows = self._parse_csv_text(text)
        return self._parse_mt5_rows(rows, symbol, timeframe, timezone)

    def load_tradingview_candles(
        self,
        file_path: str,
        symbol: str,
        timeframe: str | None = None,
        timezone: str | None = None,
        remove_duplicates: bool = True,
    ) -> list[Candle]:
        """
        Load OHLCV candles from a TradingView exported CSV file.

        Handles TradingView chart exports where the time column is either
        an ISO timestamp or a Unix epoch in seconds, plus optional symbol
        columns for multi-symbol exports.

        Args:
            file_path: Path to the TradingView CSV file.
            symbol: Default symbol (overridden by a symbol column if present).
            timeframe: Timeframe to assign (auto-detected if None).
            timezone: Source timezone (defaults to the loader config).
            remove_duplicates: Drop rows with repeated timestamps.

        Returns:
            List of Candle objects.
        """
        rows = self._read_csv(file_path)
        return self._parse_tradingview_rows(rows, symbol, timeframe, timezone, remove_duplicates)

    def load_tradingview_candles_from_text(
        self,
        text: str,
        symbol: str,
        timeframe: str | None = None,
        timezone: str | None = None,
        remove_duplicates: bool = True,
    ) -> list[Candle]:
        """Load TradingView candles from a CSV string."""
        rows = self._parse_csv_text(text)
        return self._parse_tradingview_rows(rows, symbol, timeframe, timezone, remove_duplicates)

    def load_candles_auto(
        self,
        file_path: str,
        symbol: str,
        timeframe: str | None = None,
        timezone: str | None = None,
    ) -> list[Candle]:
        """
        Load candles from any supported CSV format with auto-detection.

        Detects the format (MT5, TradingView, or generic OHLC) from the
        column headers, detects columns and timeframe automatically, and
        normalizes all timestamps to UTC.

        Args:
            file_path: Path to the CSV file.
            symbol: Symbol to assign to all candles.
            timeframe: Timeframe to assign (auto-detected if None).
            timezone: Source timezone (defaults to the loader config).

        Returns:
            List of Candle objects.

        Raises:
            ValueError: If the format or timeframe cannot be detected.
        """
        rows = self._read_csv(file_path)
        return self._parse_auto(rows, symbol, timeframe, timezone)

    def load_candles_auto_from_text(
        self,
        text: str,
        symbol: str,
        timeframe: str | None = None,
        timezone: str | None = None,
    ) -> list[Candle]:
        """Load candles from a CSV string with auto-detection."""
        rows = self._parse_csv_text(text)
        return self._parse_auto(rows, symbol, timeframe, timezone)

    def detect_format(self, header: list[str]) -> str:
        """
        Detect the CSV format from a header row.

        Returns:
            One of "mt5", "tradingview", or "generic".
        """
        norm = {h.lower().strip() for h in header}
        if {"date", "time"} <= norm and {"open", "high", "low", "close"} <= norm:
            return FORMAT_MT5
        if "time" in norm and {"open", "high", "low", "close"} <= norm:
            return FORMAT_TRADINGVIEW
        return FORMAT_GENERIC

    def detect_candle_columns(self, header: list[str]) -> CandleField:
        """
        Automatically map columns to CandleField from a header row.

        Recognizes common aliases for timestamp, open, high, low, close,
        volume, and symbol columns (case-insensitive).

        Args:
            header: List of column names.

        Returns:
            CandleField mapping.
        """
        norm = {h.lower().strip(): h for h in header}
        mapping = CandleField()
        timestamp = self._find_column(norm, ("timestamp", "datetime", "date", "time", "open_time"))
        if timestamp:
            mapping.timestamp = timestamp
        open_col = self._find_column(norm, ("open", "o"))
        if open_col:
            mapping.open = open_col
        high_col = self._find_column(norm, ("high", "h"))
        if high_col:
            mapping.high = high_col
        low_col = self._find_column(norm, ("low", "l"))
        if low_col:
            mapping.low = low_col
        close_col = self._find_column(norm, ("close", "c"))
        if close_col:
            mapping.close = close_col
        volume = self._find_column(norm, ("volume", "vol", "v"))
        if volume:
            mapping.volume = volume
        symbol = self._find_column(norm, ("symbol", "ticker"))
        if symbol:
            mapping.symbol = symbol
        return mapping

    def detect_timeframe(self, timestamps: list[datetime]) -> str:
        """
        Detect a timeframe from a list of timestamps.

        Computes the median interval between consecutive timestamps and maps
        it to a known Timeframe.

        Args:
            timestamps: Chronologically ordered list of datetimes.

        Returns:
            Timeframe value string (e.g., "1h").

        Raises:
            ValueError: If the interval cannot be matched to a timeframe.
        """
        valid = [t for t in timestamps if t is not None]
        if len(valid) < 2:
            raise ValueError("Cannot auto-detect timeframe from fewer than 2 timestamps")
        deltas = []
        for i in range(1, len(valid)):
            delta = (valid[i] - valid[i - 1]).total_seconds()
            if delta > 0:
                deltas.append(delta)
        if not deltas:
            raise ValueError("Cannot auto-detect timeframe: no positive intervals")
        median = sorted(deltas)[len(deltas) // 2]
        candidates = {tf.to_seconds(): tf.value for tf in Timeframe if tf.to_seconds() > 0}
        if median in candidates:
            return candidates[median]
        raise ValueError(f"Cannot auto-detect timeframe from median interval {median:.0f}s; pass timeframe explicitly")

    def _parse_mt5_rows(
        self,
        rows: list[dict[str, str]],
        symbol: str,
        timeframe: str | None,
        source_timezone: str | None,
    ) -> list[Candle]:
        """Parse MT5 exported rows into Candle objects."""
        if not rows:
            return []
        norm = {h.lower().strip(): h for h in rows[0].keys()}
        date_col = self._find_column(norm, ("date",))
        time_col = self._find_column(norm, ("time",))
        open_col = self._find_column(norm, ("open", "o"))
        high_col = self._find_column(norm, ("high", "h"))
        low_col = self._find_column(norm, ("low", "l"))
        close_col = self._find_column(norm, ("close", "c"))
        if not (date_col and time_col and open_col and high_col and low_col and close_col):
            raise ValueError("MT5 CSV missing required columns (Date, Time, Open, High, Low, Close)")
        tick_volume_col = self._find_column(norm, ("tick_volume", "tickvol", "tv"))
        real_volume_col = self._find_column(norm, ("real_volume", "volume", "vol"))
        spread_col = self._find_column(norm, ("spread",))
        tz = source_timezone or self.config.timezone

        timestamps = []
        for row in rows:
            try:
                timestamps.append(self._parse_mt5_datetime(row[date_col], row[time_col], tz))
            except Exception:
                timestamps.append(None)

        if timeframe is None:
            timeframe = self.detect_timeframe(timestamps)

        candles: list[Candle] = []
        for i, row in enumerate(rows):
            self._stats["total_rows"] += 1
            try:
                ts = timestamps[i]
                if ts is None:
                    raise ValueError("Invalid timestamp")
                tick_volume = None
                if tick_volume_col and row.get(tick_volume_col):
                    tick_volume = float(row[tick_volume_col])
                real_volume = None
                if real_volume_col and row.get(real_volume_col):
                    real_volume = float(row[real_volume_col])
                spread = None
                if spread_col and row.get(spread_col):
                    spread = float(row[spread_col])
                candle = Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=float(row[open_col]),
                    high=float(row[high_col]),
                    low=float(row[low_col]),
                    close=float(row[close_col]),
                    volume=tick_volume if tick_volume is not None else 0.0,
                    tick_volume=tick_volume,
                    real_volume=real_volume,
                    spread=spread,
                )
                candles.append(candle)
                self._stats["loaded_rows"] += 1
            except Exception as e:
                self._stats["error_rows"] += 1
                self._stats["errors"].append(f"Row {self._stats['total_rows']}: {e}")
                if not self.config.skip_errors:
                    raise
                self._stats["skipped_rows"] += 1
        return candles

    def _parse_tradingview_rows(
        self,
        rows: list[dict[str, str]],
        symbol: str,
        timeframe: str | None,
        source_timezone: str | None,
        remove_duplicates: bool,
    ) -> list[Candle]:
        """Parse TradingView exported rows into Candle objects."""
        if not rows:
            return []
        norm = {h.lower().strip(): h for h in rows[0].keys()}
        time_col = self._find_column(norm, ("time", "date", "datetime", "timestamp"))
        open_col = self._find_column(norm, ("open", "o"))
        high_col = self._find_column(norm, ("high", "h"))
        low_col = self._find_column(norm, ("low", "l"))
        close_col = self._find_column(norm, ("close", "c"))
        if not (time_col and open_col and high_col and low_col and close_col):
            raise ValueError("TradingView CSV missing required columns (time, open, high, low, close)")
        volume_col = self._find_column(norm, ("volume", "vol"))
        symbol_col = self._find_column(norm, ("symbol", "ticker"))
        tz = source_timezone or self.config.timezone

        timestamps = []
        for row in rows:
            try:
                value = row[time_col].strip()
                try:
                    ts = datetime.fromtimestamp(float(value), tz=timezone.utc)
                except ValueError:
                    ts = self._parse_timestamp(value, tz)
                timestamps.append(ts)
            except Exception:
                timestamps.append(None)

        if timeframe is None:
            timeframe = self.detect_timeframe(timestamps)

        candles: list[Candle] = []
        seen = set()
        for i, row in enumerate(rows):
            self._stats["total_rows"] += 1
            try:
                ts = timestamps[i]
                if ts is None:
                    raise ValueError("Invalid timestamp")
                key = ts.isoformat()
                if remove_duplicates and key in seen:
                    continue
                seen.add(key)
                row_symbol = symbol
                if symbol_col and row.get(symbol_col, "").strip():
                    row_symbol = row[symbol_col].strip()
                candle = Candle(
                    symbol=row_symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=float(row[open_col]),
                    high=float(row[high_col]),
                    low=float(row[low_col]),
                    close=float(row[close_col]),
                    volume=float(row[volume_col]) if volume_col and row.get(volume_col) else 0.0,
                )
                candles.append(candle)
                self._stats["loaded_rows"] += 1
            except Exception as e:
                self._stats["error_rows"] += 1
                self._stats["errors"].append(f"Row {self._stats['total_rows']}: {e}")
                if not self.config.skip_errors:
                    raise
                self._stats["skipped_rows"] += 1
        return candles

    def _parse_auto(
        self,
        rows: list[dict[str, str]],
        symbol: str,
        timeframe: str | None,
        source_timezone: str | None,
    ) -> list[Candle]:
        """Parse rows using automatic format/column/timeframe detection."""
        if not rows:
            return []
        fmt = self.detect_format(list(rows[0].keys()))
        if fmt == FORMAT_MT5:
            return self._parse_mt5_rows(rows, symbol, timeframe, source_timezone)
        if fmt == FORMAT_TRADINGVIEW:
            return self._parse_tradingview_rows(rows, symbol, timeframe, source_timezone, True)
        mapping = self.detect_candle_columns(list(rows[0].keys()))
        if timeframe is None:
            timestamps = []
            for row in rows:
                try:
                    timestamps.append(self._parse_timestamp(row[mapping.timestamp], source_timezone))
                except Exception:
                    timestamps.append(None)
            timeframe = self.detect_timeframe(timestamps)
        return self._parse_candles(rows, symbol, timeframe, mapping, source_timezone)

    def _parse_mt5_datetime(
        self,
        date_str: str,
        time_str: str,
        source_timezone: str,
    ) -> datetime:
        """Parse MT5 date/time columns into a UTC datetime."""
        combined = f"{date_str.strip()} {time_str.strip()}"
        formats = (
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(combined, fmt)
                break
            except ValueError:
                continue
        else:
            dt = datetime.strptime(combined, self.config.date_format)
        if self.config.normalize_timezone:
            dt = normalize_timestamp(dt, source_timezone)
        return dt

    @staticmethod
    def _find_column(header_norm: dict[str, str], aliases: tuple[str, ...]) -> str | None:
        """Find the actual column name matching one of the aliases."""
        for alias in aliases:
            if alias in header_norm:
                return header_norm[alias]
        return None

    def load_ticks(
        self,
        file_path: str,
        symbol: str,
    ) -> list[Tick]:
        """
        Load ticks from a CSV file.

        Expected columns: timestamp, price[, volume, side, bid, ask]

        Args:
            file_path: Path to the CSV file.
            symbol: Symbol to assign to all ticks.

        Returns:
            List of Tick objects.
        """
        rows = self._read_csv(file_path)
        return self._parse_ticks(rows, symbol)

    def load_quotes(
        self,
        file_path: str,
        symbol: str,
    ) -> list[Quote]:
        """
        Load quotes from a CSV file.

        Expected columns: timestamp, bid, ask[, bid_size, ask_size]

        Args:
            file_path: Path to the CSV file.
            symbol: Symbol to assign to all quotes.

        Returns:
            List of Quote objects.
        """
        rows = self._read_csv(file_path)
        return self._parse_quotes(rows, symbol)

    def load_trades(
        self,
        file_path: str,
        symbol: str,
    ) -> list[Trade]:
        """
        Load trades from a CSV file.

        Expected columns: timestamp, price, volume[, side]

        Args:
            file_path: Path to the CSV file.
            symbol: Symbol to assign to all trades.

        Returns:
            List of Trade objects.
        """
        rows = self._read_csv(file_path)
        return self._parse_trades(rows, symbol)

    def _parse_candles(
        self,
        rows: list[dict[str, str]],
        symbol: str,
        timeframe: str,
        mapping: CandleField,
        source_timezone: str | None = None,
    ) -> list[Candle]:
        """Parse rows into Candle objects."""
        candles: list[Candle] = []
        required = {mapping.timestamp, mapping.open, mapping.high, mapping.low, mapping.close}

        for row in rows:
            self._stats["total_rows"] += 1
            try:
                # Validate required fields
                missing = required - set(row.keys())
                if missing:
                    raise ValueError(f"Missing columns: {missing}")

                ts = self._parse_timestamp(row[mapping.timestamp], source_timezone)
                candle = Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=float(row[mapping.open]),
                    high=float(row[mapping.high]),
                    low=float(row[mapping.low]),
                    close=float(row[mapping.close]),
                    volume=float(row.get(mapping.volume, 0)),
                )
                candles.append(candle)
                self._stats["loaded_rows"] += 1

            except Exception as e:
                self._stats["error_rows"] += 1
                self._stats["errors"].append(f"Row {self._stats['total_rows']}: {e}")
                if not self.config.skip_errors:
                    raise
                self._stats["skipped_rows"] += 1

        return candles

    def _parse_ticks(self, rows: list[dict[str, str]], symbol: str) -> list[Tick]:
        """Parse rows into Tick objects."""
        ticks: list[Tick] = []

        for row in rows:
            self._stats["total_rows"] += 1
            try:
                ts = self._parse_timestamp(row["timestamp"])
                tick = Tick(
                    symbol=symbol,
                    timestamp=ts,
                    price=float(row.get("price", 0)),
                    volume=float(row.get("volume", 0)),
                    side=row.get("side", "unknown"),
                    bid=float(row["bid"]) if row.get("bid") else None,
                    ask=float(row["ask"]) if row.get("ask") else None,
                )
                ticks.append(tick)
                self._stats["loaded_rows"] += 1

            except Exception as e:
                self._stats["error_rows"] += 1
                self._stats["errors"].append(f"Row {self._stats['total_rows']}: {e}")
                if not self.config.skip_errors:
                    raise
                self._stats["skipped_rows"] += 1

        return ticks

    def _parse_quotes(self, rows: list[dict[str, str]], symbol: str) -> list[Quote]:
        """Parse rows into Quote objects."""
        quotes: list[Quote] = []

        for row in rows:
            self._stats["total_rows"] += 1
            try:
                ts = self._parse_timestamp(row["timestamp"])
                quote = Quote(
                    symbol=symbol,
                    timestamp=ts,
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    bid_size=float(row.get("bid_size", 0)),
                    ask_size=float(row.get("ask_size", 0)),
                )
                quotes.append(quote)
                self._stats["loaded_rows"] += 1

            except Exception as e:
                self._stats["error_rows"] += 1
                self._stats["errors"].append(f"Row {self._stats['total_rows']}: {e}")
                if not self.config.skip_errors:
                    raise
                self._stats["skipped_rows"] += 1

        return quotes

    def _parse_trades(self, rows: list[dict[str, str]], symbol: str) -> list[Trade]:
        """Parse rows into Trade objects."""
        trades: list[Trade] = []

        for row in rows:
            self._stats["total_rows"] += 1
            try:
                ts = self._parse_timestamp(row["timestamp"])
                trade = Trade(
                    symbol=symbol,
                    timestamp=ts,
                    price=float(row["price"]),
                    volume=float(row.get("volume", 0)),
                    side=row.get("side", "unknown"),
                )
                trades.append(trade)
                self._stats["loaded_rows"] += 1

            except Exception as e:
                self._stats["error_rows"] += 1
                self._stats["errors"].append(f"Row {self._stats['total_rows']}: {e}")
                if not self.config.skip_errors:
                    raise
                self._stats["skipped_rows"] += 1

        return trades

    def _parse_timestamp(self, value: str, source_timezone: str | None = None) -> datetime:
        """Parse a timestamp string, with timezone normalization."""
        try:
            dt = _parse_iso_compat(value)
        except (ValueError, TypeError):
            dt = datetime.strptime(value, self.config.date_format)

        if self.config.normalize_timezone:
            dt = normalize_timestamp(dt, source_timezone or self.config.timezone)

        return dt

    def _read_csv(self, file_path: str) -> list[dict[str, str]]:
        """Read a CSV file and return rows as dicts."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"CSV file not found: {file_path}")

        with open(file_path, encoding="utf-8-sig") as f:
            return self._parse_csv_reader(f)

    def _parse_csv_text(self, text: str) -> list[dict[str, str]]:
        """Parse CSV text and return rows as dicts."""
        return self._parse_csv_reader(io.StringIO(text))

    def _parse_csv_reader(self, source: io.TextIOBase) -> list[dict[str, str]]:
        """Parse CSV from a reader source."""
        reader = csv.DictReader(source, delimiter=self.config.delimiter)
        rows: list[dict[str, str]] = []
        for row in reader:
            # Strip whitespace from keys and values; tolerate missing cells.
            cleaned = {
                k.strip(): (v.strip() if v is not None else "")
                for k, v in row.items()
                if k is not None
            }
            rows.append(cleaned)
        return rows

    def load_ticks_from_text(
        self,
        text: str,
        symbol: str,
    ) -> list[Tick]:
        """
        Load ticks from a CSV string.

        Args:
            text: CSV content as a string.
            symbol: Symbol to assign to all ticks.

        Returns:
            List of Tick objects.
        """
        rows = self._parse_csv_text(text)
        return self._parse_ticks(rows, symbol)

    def load_quotes_from_text(
        self,
        text: str,
        symbol: str,
    ) -> list[Quote]:
        """
        Load quotes from a CSV string.

        Args:
            text: CSV content as a string.
            symbol: Symbol to assign to all quotes.

        Returns:
            List of Quote objects.
        """
        rows = self._parse_csv_text(text)
        return self._parse_quotes(rows, symbol)

    def load_trades_from_text(
        self,
        text: str,
        symbol: str,
    ) -> list[Trade]:
        """
        Load trades from a CSV string.

        Args:
            text: CSV content as a string.
            symbol: Symbol to assign to all trades.

        Returns:
            List of Trade objects.
        """
        rows = self._parse_csv_text(text)
        return self._parse_trades(rows, symbol)

    def reset_stats(self) -> None:
        """Reset loading statistics."""
        self._stats = {
            "total_rows": 0,
            "loaded_rows": 0,
            "skipped_rows": 0,
            "error_rows": 0,
            "errors": [],
        }
