"""Phase 5.2 source timestamp and scalar-series adapters.

The Phase 5.2 macro boundary accepts both OHLC-style secondary series and
scalar daily observations such as FRED DGS10/VIXCLS. Scalar observations are
kept as value+timestamp records; no OHLC values are fabricated and no missing
observations are repaired.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone

from researchos.data_engine.candle import Candle
from researchos.data_engine.csv_loader import CsvLoader


@dataclass(frozen=True)
class ScalarObservation:
    """A timestamped scalar macro observation used by Phase 5.2."""

    timestamp: datetime
    close: float


def normalize_epoch_timestamp_csv(text: str) -> str:
    """Canonicalize numeric epoch timestamps to UTC ISO-8601 strings.

    The raw source text is not modified. This adapter exists only at the
    Phase 5.2 ingestion boundary so source-specific epoch units do not leak
    into the strict Data Engine timestamp parser.

    Supported numeric epoch units are seconds and milliseconds. Unit is
    inferred from magnitude using conservative Unix-epoch bounds.
    Non-numeric timestamps are returned unchanged so existing ISO/date
    formats continue through the normal Data Engine parser.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header")
    timestamp_column = next(
        (name for name in reader.fieldnames if name.strip().lower() in {"timestamp", "time", "datetime", "date"}),
        None,
    )
    if timestamp_column is None:
        return text

    rows = list(reader)
    for row in rows:
        raw = (row.get(timestamp_column) or "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        absolute = abs(value)
        if absolute >= 100_000_000_000:
            seconds = value / 1_000.0
        elif absolute >= 1_000_000_000:
            seconds = float(value)
        else:
            continue
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        row[timestamp_column] = dt.isoformat().replace("+00:00", "Z")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def load_fred_scalar_series_from_text(text: str) -> list[ScalarObservation] | None:
    """Parse a FRED date/scalar CSV without manufacturing OHLC data.

    Expected shape is ``observation_date,<series>`` (for example
    ``observation_date,DGS10`` or ``observation_date,VIXCLS``). Rows with
    FRED's ``.`` missing-value marker are excluded from the observation set;
    they are not forward-filled or interpolated.
    """
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    normalized = {name.strip().lower(): name for name in fieldnames}
    date_column = normalized.get("observation_date")
    if date_column is None:
        return None

    value_columns = [name for name in fieldnames if name != date_column]
    if len(value_columns) != 1:
        return None
    value_column = value_columns[0]

    observations: list[ScalarObservation] = []
    for row in reader:
        raw_date = (row.get(date_column) or "").strip()
        raw_value = (row.get(value_column) or "").strip()
        if not raw_date or not raw_value or raw_value == ".":
            continue
        try:
            dt = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid FRED scalar observation: {row}") from exc
        observations.append(ScalarObservation(timestamp=dt, close=value))

    return observations


# Phase 5.2's existing experiment boundary calls the Data Engine auto loader
# for all macro inputs. Install a narrow adapter there so FRED scalar sources
# enter as value+timestamp observations while all other CSVs retain the
# original loader path. This does not alter the raw source or repair data.
def _install_fred_scalar_adapter() -> None:
    original = CsvLoader.load_candles_auto_from_text
    if getattr(original, "_phase52_fred_scalar_adapter", False):
        return

    def load_candles_auto_from_text_phase52(
        self: CsvLoader,
        text: str,
        symbol: str,
        timeframe: str | None = None,
        timezone: str | None = None,
    ) -> list[ScalarObservation] | list[Candle]:
        observations = load_fred_scalar_series_from_text(text)
        if observations is not None:
            return observations
        return original(self, text, symbol, timeframe, timezone)

    setattr(load_candles_auto_from_text_phase52, "_phase52_fred_scalar_adapter", True)
    setattr(CsvLoader, "load_candles_auto_from_text", load_candles_auto_from_text_phase52)


_install_fred_scalar_adapter()
