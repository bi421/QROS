"""Evidence-first operational and forward-return evaluation for processed QROS streams.

Evaluates existing decisions; it does not generate signals or claim predictive edge.
Rows must be in chronological decision order, one row per tick/bar, with positive close.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any

import numpy as np
import polars as pl


@dataclass(frozen=True)
class EvaluationConfig:
    state_col: str = "state"
    close_col: str = "close"
    latency_col: str = "latency_ms"
    safety_trigger_col: str = "safety_gate_triggered"
    safety_passed_col: str = "safety_passed"
    safety_reason_col: str = "safety_gate_reason"
    vxy_col: str = "vxy_level"
    horizons: tuple[int, ...] = (1, 5, 10)


class QROSPipelineEvaluator:
    """Compute decision distribution, safety, latency, forward-return and throughput metrics.

    Required columns are state in {-1, 0, +1} and close. Optional diagnostics include
    latency_ms, safety_gate_triggered (preferred), safety_passed, and safety_gate_reason.
    Forward returns are signed close-to-close returns, not simulated net trade P&L.
    """

    def __init__(self, config: EvaluationConfig | None = None) -> None:
        self.config = config or EvaluationConfig()
        self._frame: pl.DataFrame | None = None
        self._ingest_seconds = 0.0
        self._metrics: dict[str, Any] | None = None

    def ingest(self, frame: pl.DataFrame) -> "QROSPipelineEvaluator":
        """Validate and retain the processed Polars DataFrame."""
        started = time.perf_counter()
        if not isinstance(frame, pl.DataFrame):
            raise TypeError("frame must be a polars.DataFrame")
        cfg = self.config
        missing = [name for name in (cfg.state_col, cfg.close_col) if name not in frame.columns]
        if missing:
            raise ValueError(f"missing required columns: {missing}")
        if frame.height == 0:
            raise ValueError("cannot evaluate an empty dataframe")
        try:
            raw_states = frame.get_column(cfg.state_col).cast(pl.Float64, strict=True).to_numpy()
            closes = frame.get_column(cfg.close_col).cast(pl.Float64, strict=True).to_numpy()
        except Exception as exc:
            raise ValueError("state must be integer-like and close must be numeric") from exc
        valid_states = np.isfinite(raw_states) & np.isin(raw_states, (-1.0, 0.0, 1.0))
        if not valid_states.all():
            invalid = np.unique(raw_states[~valid_states]).tolist()
            raise ValueError(f"state values must be exactly -1, 0, or +1; found {invalid}")
        states = raw_states.astype(np.int8)
        if not np.isfinite(closes).all() or (closes <= 0).any():
            raise ValueError("close prices must be finite and strictly positive")
        for horizon in cfg.horizons:
            if not isinstance(horizon, int) or horizon < 1:
                raise ValueError("horizons must contain positive integers")
        if len(set(cfg.horizons)) != len(cfg.horizons):
            raise ValueError("horizons must be unique")
        self._frame = frame.clone()
        self._metrics = None
        self._ingest_seconds = time.perf_counter() - started
        return self

    def _safety_mask(self, frame: pl.DataFrame) -> np.ndarray:
        cfg = self.config
        if cfg.safety_trigger_col in frame.columns:
            return frame.get_column(cfg.safety_trigger_col).fill_null(False).cast(pl.Boolean).to_numpy().astype(bool)
        if cfg.safety_passed_col in frame.columns:
            passed = frame.get_column(cfg.safety_passed_col).fill_null(False).cast(pl.Boolean).to_numpy()
            return ~passed.astype(bool)
        if cfg.safety_reason_col in frame.columns:
            reasons = frame.get_column(cfg.safety_reason_col).cast(pl.String).fill_null("").to_list()
            return np.array([bool(str(x).strip()) and str(x).strip().lower() not in {"none", "ok", "passed"} for x in reasons])
        return np.zeros(frame.height, dtype=bool)

    def _safety_causes(self, frame: pl.DataFrame, mask: np.ndarray) -> dict[str, int]:
        cfg = self.config
        causes = {"latency": 0, "vxy": 0, "other_or_unclassified": 0}
        if cfg.safety_reason_col not in frame.columns:
            causes["other_or_unclassified"] = int(mask.sum())
            return causes
        reasons = frame.get_column(cfg.safety_reason_col).cast(pl.String).fill_null("").to_list()
        for triggered, reason in zip(mask, reasons):
            if not triggered:
                continue
            normalized = str(reason).lower()
            if any(token in normalized for token in ("latency", "timeout", "ingest_lag", "network")):
                causes["latency"] += 1
            elif any(token in normalized for token in ("vxy", "volatility", "vol_regime")):
                causes["vxy"] += 1
            else:
                causes["other_or_unclassified"] += 1
        return causes

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float | None:
        return float(numerator / denominator) if denominator else None

    def _forward_metrics(self, states: np.ndarray, closes: np.ndarray,
                         safety: np.ndarray, horizon: int) -> dict[str, Any]:
        n = len(closes)
        valid_n = max(0, n - horizon)
        if not valid_n:
            return {"horizon": horizon, "eligible_signals": 0, "evaluated_signals": 0,
                    "win_rate": None, "profit_factor": None, "expectancy": None,
                    "mean_forward_return": None, "safety_excluded_signals": 0,
                    "clean_win_rate": None, "clean_profit_factor": None,
                    "clean_expectancy": None, "clean_evaluated_signals": 0}
        forward = closes[horizon:] / closes[:-horizon] - 1.0
        decision_states = states[:valid_n]
        decision_safety = safety[:valid_n]
        signed = forward * decision_states
        valid = (decision_states != 0) & np.isfinite(signed)

        def summarize(mask: np.ndarray) -> dict[str, Any]:
            values = signed[mask]
            wins, losses = values[values > 0], values[values < 0]
            gross_profit = float(wins.sum()) if len(wins) else 0.0
            gross_loss = float(-losses.sum()) if len(losses) else 0.0
            return {
                "win_rate": float(np.mean(values > 0)) if len(values) else None,
                "profit_factor": self._ratio(gross_profit, gross_loss),
                "expectancy": float(np.mean(values)) if len(values) else None,
                "mean_forward_return": float(np.mean(values)) if len(values) else None,
                "evaluated_signals": int(len(values)),
            }
        all_stats = summarize(valid)
        clean_stats = summarize(valid & ~decision_safety)
        return {
            "horizon": horizon, "eligible_signals": int((decision_states != 0).sum()),
            **all_stats, "safety_excluded_signals": int((valid & decision_safety).sum()),
            "clean_win_rate": clean_stats["win_rate"],
            "clean_profit_factor": clean_stats["profit_factor"],
            "clean_expectancy": clean_stats["expectancy"],
            "clean_evaluated_signals": clean_stats["evaluated_signals"],
        }

    def compute(self) -> dict[str, Any]:
        """Compute metrics. Missing safety data is explicitly reported, not inferred."""
        frame = self._require_frame()
        started = time.perf_counter()
        cfg = self.config
        states = frame.get_column(cfg.state_col).cast(pl.Int8).to_numpy()
        closes = frame.get_column(cfg.close_col).cast(pl.Float64).to_numpy()
        safety = self._safety_mask(frame)
        n = frame.height
        counts = {str(s): int(np.count_nonzero(states == s)) for s in (-1, 0, 1)}
        shares = {key: value / n for key, value in counts.items()}
        safety_count = int(safety.sum())
        latency: dict[str, Any] = {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "p99_ms": None}
        if cfg.latency_col in frame.columns:
            vals = frame.get_column(cfg.latency_col).cast(pl.Float64, strict=True).to_numpy()
            vals = vals[np.isfinite(vals)]
            latency = {
                "count": int(len(vals)),
                "mean_ms": float(np.mean(vals)) if len(vals) else None,
                "median_ms": float(np.median(vals)) if len(vals) else None,
                "p95_ms": float(np.percentile(vals, 95)) if len(vals) else None,
                "p99_ms": float(np.percentile(vals, 99)) if len(vals) else None,
            }
        causes = self._safety_causes(frame, safety)
        alpha = {str(h): self._forward_metrics(states, closes, safety, h) for h in cfg.horizons}
        compute_seconds = time.perf_counter() - started
        elapsed = self._ingest_seconds + compute_seconds
        trigger_source = (
            cfg.safety_trigger_col if cfg.safety_trigger_col in frame.columns else
            cfg.safety_passed_col if cfg.safety_passed_col in frame.columns else
            cfg.safety_reason_col if cfg.safety_reason_col in frame.columns else
            "not_supplied_assumed_no_triggers"
        )
        self._metrics = {
            "rows": n,
            "decision_distribution": {
                "counts": counts, "shares": shares,
                "active_count": counts["-1"] + counts["1"],
                "active_share": (counts["-1"] + counts["1"]) / n,
                "sideline_count": counts["0"], "sideline_share": shares["0"],
            },
            "safety_gate": {
                "trigger_count": safety_count, "trigger_share": safety_count / n,
                "root_causes": {k: {"count": v, "share_of_all_rows": v / n} for k, v in causes.items()},
                "triggered_non_neutral_state_count": int(np.count_nonzero(safety & (states != 0))),
                "source": trigger_source,
            },
            "latency": latency,
            "forward_returns": alpha,
            "profiling": {
                "ingest_validation_seconds": self._ingest_seconds,
                "compute_seconds": compute_seconds, "evaluator_total_seconds": elapsed,
                "evaluator_ticks_per_second": n / elapsed if elapsed > 0 else None,
                "scope": "evaluator only; upstream tick-processing latency is not measured",
            },
            "caveats": [
                "Forward returns are signed close-to-close returns, not net P&L; fees, spread, slippage and execution delay are excluded.",
                "Rows are assumed to be in chronological decision order; no implicit sorting is performed.",
                "Clean metrics exclude signals whose decision row has Safety Gate triggered; this alone does not prove toxicity avoidance.",
                "Predictive edge requires leakage-safe out-of-sample evaluation, uncertainty intervals and a declared baseline.",
            ],
        }
        return self._metrics

    def _require_frame(self) -> pl.DataFrame:
        if self._frame is None:
            raise RuntimeError("call ingest(frame) before compute()")
        return self._frame

    def dashboard(self) -> str:
        """Return a formatted operational and predictive-diagnostic dashboard."""
        m = self._metrics if self._metrics is not None else self.compute()
        d, g, lat, p = m["decision_distribution"], m["safety_gate"], m["latency"], m["profiling"]
        lines = [
            "=" * 72, "QROS PIPELINE EVALUATION — OPERATIONAL / DIAGNOSTIC SUMMARY", "=" * 72,
            f"Rows evaluated: {m['rows']:,}", "DECISION DISTRIBUTION",
            f"  Bullish (+1): {d['counts']['1']:,} ({d['shares']['1']:.2%})",
            f"  Bearish (-1): {d['counts']['-1']:,} ({d['shares']['-1']:.2%})",
            f"  Neutral ( 0): {d['sideline_count']:,} ({d['sideline_share']:.2%})",
            f"  Active vs sideline: {d['active_share']:.2%} / {d['sideline_share']:.2%}",
            "SAFETY GATE",
            f"  Triggered: {g['trigger_count']:,} ({g['trigger_share']:.2%}) [source: {g['source']}]",
            f"  Triggered rows not neutral (contract violation): {g['triggered_non_neutral_state_count']:,}",
        ]
        for name, item in g["root_causes"].items():
            lines.append(f"  {name}: {item['count']:,} ({item['share_of_all_rows']:.2%} of rows)")
        lines.extend([
            "LATENCY",
            f"  n={lat['count']:,} mean={self._fmt(lat['mean_ms'])} ms median={self._fmt(lat['median_ms'])} ms "
            f"p95={self._fmt(lat['p95_ms'])} ms p99={self._fmt(lat['p99_ms'])} ms",
            "FORWARD SIGNAL METRICS (signed close-to-close return; not net P&L)",
        ])
        for horizon, item in m["forward_returns"].items():
            lines.append(
                f"  t+{horizon}: n={item['evaluated_signals']:,} win={self._pct(item['win_rate'])} "
                f"PF={self._fmt(item['profit_factor'])} expectancy={self._pct(item['expectancy'])}; "
                f"clean n={item['clean_evaluated_signals']:,} win={self._pct(item['clean_win_rate'])} "
                f"PF={self._fmt(item['clean_profit_factor'])} exp={self._pct(item['clean_expectancy'])}"
            )
        lines.extend([
            "EVALUATOR PROFILING",
            f"  ingest/validation={p['ingest_validation_seconds']:.6f}s compute={p['compute_seconds']:.6f}s "
            f"total={p['evaluator_total_seconds']:.6f}s throughput={self._fmt(p['evaluator_ticks_per_second'])} rows/s",
            "LIMITATIONS",
            "  Evaluator throughput is not upstream live-stream throughput.",
            "  Returns exclude transaction costs and are not an execution/backtest simulation.",
            "  No alpha claim is supported without leakage-safe out-of-sample tests.", "=" * 72,
        ])
        return "\n".join(lines)

    def print_dashboard(self) -> None:
        print(self.dashboard())

    @staticmethod
    def _fmt(value: Any) -> str:
        if value is None or (isinstance(value, (float, np.floating)) and not math.isfinite(float(value))):
            return "N/A"
        return f"{float(value):.6g}"

    @classmethod
    def _pct(cls, value: Any) -> str:
        return "N/A" if value is None else f"{100 * float(value):.3f}%"
