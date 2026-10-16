"""Stream a CSV and print exactly one final state: UP, DOWN, or RANGE."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from researchos.orchestration.fast_three_state import FastThreeState


def classify_csv(
    path: Path,
    *,
    close_column: str = "close",
    lookback: int = 32,
    efficiency_threshold: float = 0.35,
    min_move_bps: float = 5.0,
) -> str:
    engine = FastThreeState(
        lookback=lookback,
        efficiency_threshold=efficiency_threshold,
        min_move_bps=min_move_bps,
    )
    rows = 0
    state = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header")
        columns = {name.strip().lower(): name for name in reader.fieldnames}
        actual_column = columns.get(close_column.strip().lower())
        if actual_column is None:
            raise ValueError(f"CSV missing close column: {close_column}")
        for row in reader:
            close = float(row[actual_column])
            if not math.isfinite(close) or close <= 0.0:
                raise ValueError("CSV contains invalid close")
            state = engine.update(close)
            rows += 1
    if rows == 0:
        raise ValueError("CSV contains no candles")
    return _state_name(state)


def _state_name(state: int) -> str:
    return "UP" if state == 1 else "DOWN" if state == -1 else "RANGE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--lookback", type=int, default=32)
    parser.add_argument("--efficiency-threshold", type=float, default=0.35)
    parser.add_argument("--min-move-bps", type=float, default=5.0)
    args = parser.parse_args()
    print(classify_csv(
        args.csv_path,
        close_column=args.close_column,
        lookback=args.lookback,
        efficiency_threshold=args.efficiency_threshold,
        min_move_bps=args.min_move_bps,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
