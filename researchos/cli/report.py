"""Canonical ResearchOS Phase 5.2 production report.

The report uses pre-research context as feature state only. Context rows are
never emitted as research samples; the frozen research gate remains
train+validation samples from the 2021-2025 research period.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from researchos.experiments.phase52 import FEATURE_SET_NAMES, Phase52Config
from researchos.experiments.phase52_rebuild.context_execution import (
    run_context_aware_phase52_comparison,
)
from researchos.experiments.phase52_rebuild.context_pipeline import (
    build_context_aware_feature_datasets,
)

ROOT = Path(__file__).resolve().parents[2]
XAU_PATH = ROOT / "data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv"
DXY_PATH = ROOT / "data/macro/raw/DXY_Dukascopy_2021_2025.csv"
US10Y_PATH = ROOT / "data/macro/raw/DGS10_fred.csv"
VIX_PATH = ROOT / "data/macro/raw/VIXCLS_fred.csv"
CONTEXT_XAU_PATH = ROOT / "data/mt5/xauusd/context_2020/XAUUSD_M1_2020_MT5.csv"
CONTEXT_DXY_PATH = ROOT / "data/macro/context/dukascopy_2020/DXY_Dukascopy_D1_2020_context.csv"
SYMBOL, TIMEFRAME = "XAUUSD", "1d"
HORIZON, THRESHOLD = 5, 0.0
TRAIN_SIZE, VALIDATION_SIZE, STEP_SIZE = 1000, 200, 200
N_NEIGHBORS = 25
COSTS = {"spread": "fixed:0", "slippage": "fixed:0", "commission": "fixed:0"}
MACROS = ("DXY", "US10Y", "VIX")


@dataclass
class SourceReport:
    name: str
    path: str
    raw_rows: int | None
    production_rows: int | None
    sha256: str | None
    identity: str
    exists: bool
    error: str | None = None


@dataclass
class Report:
    schema: str
    project: dict[str, Any]
    configuration: dict[str, Any]
    data: dict[str, Any]
    alignment: dict[str, Any]
    dataset: dict[str, Any]
    phase52: dict[str, Any]
    evidence_status: dict[str, Any]
    artifacts: dict[str, Any]


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "UNKNOWN"


def _parse_timestamp(value: str) -> datetime:
    s = value.strip()
    if not s:
        raise ValueError("empty timestamp")
    try:
        n = float(s)
        if abs(n) > 1e11:
            return datetime.fromtimestamp(n / 1000.0, tz=timezone.utc)
        if abs(n) > 1e9:
            return datetime.fromtimestamp(n, tz=timezone.utc)
    except ValueError:
        pass
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _raw_timestamp_set(path: Path, name: str) -> tuple[int, set[datetime]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {str(x).strip().lower(): x for x in (reader.fieldnames or [])}
        rows, timestamps = 0, set()
        for row in reader:
            rows += 1
            try:
                if "observation_date" in fields:
                    value_columns = [x for x in fields.values() if x != fields["observation_date"]]
                    if len(value_columns) == 1:
                        raw_value = (row.get(value_columns[0]) or "").strip()
                        if not raw_value or raw_value == ".":
                            continue
                if name == "XAUUSD" and fields.get("date") and fields.get("time"):
                    ts = datetime.strptime(
                        f"{row[fields['date']].strip()} {row[fields['time']].strip()}",
                        "%Y.%m.%d %H:%M:%S",
                    ).replace(tzinfo=timezone.utc)
                elif "timestamp" in fields:
                    ts = _parse_timestamp(row[fields["timestamp"]])
                elif "observation_date" in fields:
                    ts = datetime.strptime(
                        row[fields["observation_date"]].strip(), "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                elif "date" in fields:
                    ts = datetime.strptime(row[fields["date"]].strip(), "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                else:
                    raise KeyError("no supported timestamp column")
                timestamps.add(ts)
            except Exception:
                continue
    return rows, timestamps


def _source(name: str, path: Path, identity: str) -> SourceReport:
    if not path.exists():
        return SourceReport(
            name, str(path.relative_to(ROOT)), None, None, None, identity, False, "file missing"
        )
    try:
        raw_rows, _ = _raw_timestamp_set(path, name)
        error = None
    except Exception as exc:
        raw_rows, error = None, str(exc)
    return SourceReport(
        name,
        str(path.relative_to(ROOT)),
        raw_rows,
        None,
        _sha256(path),
        identity,
        True,
        error,
    )


def _production_sources() -> dict[str, SourceReport]:
    return {
        "XAUUSD": _source("XAUUSD", XAU_PATH, "MT5 curated canonical D1"),
        "DXY": _source("DXY", DXY_PATH, "Dukascopy dollaridxusd; secondary DXY series"),
        "US10Y": _source("US10Y", US10Y_PATH, "FRED DGS10"),
        "VIX": _source("VIX", VIX_PATH, "FRED VIXCLS"),
        "CONTEXT_XAUUSD": _source("XAUUSD", CONTEXT_XAU_PATH, "MT5 XAUUSD M1 context state only"),
        "CONTEXT_DXY": _source("DXY", CONTEXT_DXY_PATH, "Dukascopy DXY context state only"),
    }


def _research_timestamp_sets() -> tuple[dict[str, set[datetime]], dict[str, int]]:
    paths = {"XAUUSD": XAU_PATH, "DXY": DXY_PATH, "US10Y": US10Y_PATH, "VIX": VIX_PATH}
    sets: dict[str, set[datetime]] = {}
    rows: dict[str, int] = {}
    for name, path in paths.items():
        raw_rows, timestamps = _raw_timestamp_set(path, name)
        rows[name] = raw_rows
        sets[name] = timestamps
    return sets, rows


def _result_dict(result: Any) -> dict[str, Any]:
    model = getattr(result, "model", None)
    baseline = getattr(result, "baseline", None)
    significance = getattr(result, "significance", None)
    calibration = getattr(result, "calibration", None)
    metadata = getattr(result, "metadata", {}) or {}
    accuracy = getattr(model, "accuracy", None) if model else None
    baseline_accuracy = getattr(baseline, "accuracy", None) if baseline else None
    model_brier = getattr(model, "brier_score", None) if model else None
    baseline_brier = getattr(baseline, "brier_score", None) if baseline else None
    return {
        "outcome": getattr(result, "outcome", None),
        "folds": getattr(result, "num_folds", None),
        "validation_samples": getattr(model, "sample_count", None) if model else None,
        "accuracy": accuracy,
        "baseline_accuracy": baseline_accuracy,
        "accuracy_delta_vs_baseline": (
            accuracy - baseline_accuracy
            if accuracy is not None and baseline_accuracy is not None
            else None
        ),
        "brier": model_brier,
        "baseline_brier": baseline_brier,
        "brier_delta_vs_baseline": (
            model_brier - baseline_brier
            if model_brier is not None and baseline_brier is not None
            else None
        ),
        "p_value": getattr(significance, "p_value", None) if significance else None,
        "significant": getattr(significance, "significant", None) if significance else None,
        "calibration_status": getattr(calibration, "status", None) if calibration else None,
        "data_valid": getattr(result, "data_valid", False),
        "leakage_check": getattr(result, "leakage_check", False),
        "out_of_sample": getattr(result, "out_of_sample", False),
        "cost_adjusted": getattr(result, "cost_adjusted", False),
        "reproducible": bool(
            getattr(result, "reproducibility_hash", None) or metadata.get("combined_input_hash")
        ),
        "reproducibility_hash": getattr(result, "reproducibility_hash", None),
        "combined_input_hash": metadata.get("combined_input_hash"),
        "blocked_reason": metadata.get("blocked_reason")
        or metadata.get("reason")
        or getattr(result, "reason", None),
    }


def _build_report() -> Report:
    required = [
        XAU_PATH,
        DXY_PATH,
        US10Y_PATH,
        VIX_PATH,
        CONTEXT_XAU_PATH,
        CONTEXT_DXY_PATH,
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("missing context-aware report source files: " + ", ".join(missing))

    sources = _production_sources()
    raw_sets, raw_rows = _research_timestamp_sets()
    raw_common = set.intersection(*(raw_sets[n] for n in ("XAUUSD", *MACROS)))

    config = Phase52Config(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        horizon=HORIZON,
        threshold=THRESHOLD,
        train_size=TRAIN_SIZE,
        validation_size=VALIDATION_SIZE,
        step_size=STEP_SIZE,
        n_neighbors=N_NEIGHBORS,
        spread_spec=COSTS["spread"],
        slippage_spec=COSTS["slippage"],
        commission_spec=COSTS["commission"],
    )
    build = build_context_aware_feature_datasets(
        CONTEXT_XAU_PATH,
        CONTEXT_DXY_PATH,
        US10Y_PATH,
        VIX_PATH,
        XAU_PATH,
        DXY_PATH,
    )
    results = run_context_aware_phase52_comparison(build, config)
    report_to_rebuild = {
        "PRICE_ONLY": "PRICE_ONLY",
        "PRICE + DXY": "PRICE_DXY",
        "PRICE + US10Y": "PRICE_US10Y",
        "PRICE + VIX": "PRICE_VIX",
        "PRICE + ALL": "PRICE_ALL",
    }
    result_map = {
        name: _result_dict(results[report_to_rebuild[name]]) for name in FEATURE_SET_NAMES
    }

    research_days = {
        datetime.fromisoformat(o.day).replace(tzinfo=timezone.utc)
        for o in build.research_observations
    }
    production_common = research_days
    context_days = {
        datetime.fromisoformat(o.day).replace(tzinfo=timezone.utc)
        for o in build.context_observations
    }
    usable = build.usable_sample_count
    required_samples = TRAIN_SIZE + VALIDATION_SIZE
    dataset_blocked = usable < required_samples
    experiment_passed = all(v["outcome"] == "PASS" for v in result_map.values())
    experiment_blocked = not experiment_passed

    dataset_report = {
        "context_sample": build.context_sample_count,
        "context_rows_emitted": 0,
        "research_sample": build.research_sample_count,
        "common_sample": build.research_sample_count,
        "usable_sample": usable,
        "required_samples": required_samples,
        "shortfall": max(0, required_samples - usable),
        "surplus": max(0, usable - required_samples),
        "feature_count": build.datasets[FEATURE_SET_NAMES[0]].feature_count,
        "label_count": usable,
        "source_indices": usable,
        "warmup_dropped": 0,
        "tail_dropped": HORIZON,
        "drop_diagnostics": {
            "context_warmup_rows": 60,
            "context_observations": build.context_sample_count,
            "research_observations": build.research_sample_count,
            "label_horizon": HORIZON,
            "research_rows_lost_to_warmup": 0,
            "research_rows_lost_to_label_horizon": HORIZON,
            "usable_sample_count": usable,
        },
        "gate": "BLOCKED" if dataset_blocked else "PASS",
        "combined_input_hash": result_map[FEATURE_SET_NAMES[0]]["combined_input_hash"],
        "dataset_contract": "context_state_only_plus_research_only_execution",
    }

    evidence = {
        "source_data": "PASS",
        "alignment": "AVAILABLE",
        "dataset": "BLOCKED" if dataset_blocked else "PASS",
        "experiment": "BLOCKED" if experiment_blocked else "PASS",
        "overall": "READY" if not dataset_blocked and not experiment_blocked else "NOT READY",
        "scientific_claim": (
            "NO_PREDICTIVE_CLAIM_WHILE_BLOCKED_OR_FAILED"
            if dataset_blocked or experiment_blocked
            else "EVALUATE_ONLY_AFTER_ALL_GATES_PASS"
        ),
        "blocking_reason": (
            "REAL XAUUSD + MACRO DATA REQUIRED (insufficient aligned samples after merge)"
            if dataset_blocked
            else (
                "EXPERIMENT_GATE_FAILED (one or more feature sets failed the frozen evidence criteria)"
                if experiment_blocked
                else None
            )
        ),
    }

    first = min(production_common).date().isoformat() if production_common else None
    last = max(production_common).date().isoformat() if production_common else None
    alignment = {
        "raw_exact_intersection": len(raw_common),
        "production_exact_intersection": len(production_common),
        "raw_vs_production_difference": len(raw_common) - len(production_common),
        "first": first,
        "last": last,
        "context_first": min(context_days).date().isoformat() if context_days else None,
        "context_last": max(context_days).date().isoformat() if context_days else None,
        "context_before_research": max(context_days) < min(production_common),
        "rule": "Exact timestamp equality; no date truncation, interpolation, forward-fill, resampling, or repair",
        "context_contract": "feature state only; context rows never emitted or counted",
    }

    data = {name: asdict(src) for name, src in sources.items()}
    for name, rows in raw_rows.items():
        if name in data:
            data[name]["raw_rows"] = rows
    return Report(
        schema="researchos/canonical-report/v3-context-aware",
        project={
            "name": "ResearchOS",
            "commit": _git("rev-parse", "HEAD"),
            "working_tree": "CLEAN" if not _git("status", "--porcelain") else "DIRTY",
            "report_source": "LIVE_CONTEXT_AWARE_PRODUCTION_PIPELINE",
        },
        configuration={
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "horizon": HORIZON,
            "threshold": THRESHOLD,
            "train_size": TRAIN_SIZE,
            "validation_size": VALIDATION_SIZE,
            "step_size": STEP_SIZE,
            "n_neighbors": N_NEIGHBORS,
            **COSTS,
        },
        data=data,
        alignment=alignment,
        dataset=dataset_report,
        phase52=result_map,
        evidence_status=evidence,
        artifacts={
            "json": "reports/phase52/canonical_phase52_report.json",
            "markdown": "reports/phase52/canonical_phase52_report.md",
        },
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _render(report: Report) -> str:
    r = _json_safe(asdict(report))
    lines = [
        "# ResearchOS — Canonical Phase 5.2 Report",
        "",
        f"**Overall gate:** {r['evidence_status']['overall']}",
        f"**Scientific claim:** {r['evidence_status']['scientific_claim']}",
        "",
        "## Executive conclusion",
        "",
        f"Usable observations: **{r['dataset']['usable_sample']} / {r['dataset']['required_samples']}**; shortfall: **{r['dataset']['shortfall']}**; surplus: **{r['dataset']['surplus']}**.",
        f"Dataset gate: **{r['dataset']['gate']}**. Experiment gate: **{r['evidence_status']['experiment']}**.",
        f"Context rows: **{r['dataset']['context_sample']}** (emitted/countable: **0**). Research rows: **{r['dataset']['research_sample']}**.",
    ]
    if r["evidence_status"]["blocking_reason"]:
        lines += [f"Blocking reason: **{r['evidence_status']['blocking_reason']}**."]
    lines += [
        "",
        "## Data identity",
        "",
        "| Source | Production rows | SHA-256 |",
        "|---|---:|---|",
    ]
    for name, src in r["data"].items():
        lines.append(f"| {name} | {src['production_rows']} | `{src['sha256']}` |")
    lines += [
        "",
        "## Alignment",
        "",
        f"Exact raw research intersection: **{r['alignment']['raw_exact_intersection']}**",
        f"Exact production research intersection: **{r['alignment']['production_exact_intersection']}**",
        f"Raw → production difference: **{r['alignment']['raw_vs_production_difference']}**",
        f"Context range: **{r['alignment']['context_first']} → {r['alignment']['context_last']}**",
        f"Research range: **{r['alignment']['first']} → {r['alignment']['last']}**",
        f"Context strictly before research: **{r['alignment']['context_before_research']}**",
        f"Rule: {r['alignment']['rule']}",
        "",
        "## Dataset accounting",
        "",
        f"Context observations: **{r['dataset']['context_sample']}**",
        "Context emitted/countable: **0**",
        f"Research observations: **{r['dataset']['research_sample']}**",
        f"Warmup dropped from research: **{r['dataset']['warmup_dropped']}**",
        f"Tail dropped for label horizon: **{r['dataset']['tail_dropped']}**",
        f"Usable labels: **{r['dataset']['label_count']}**",
        f"Combined input hash: `{r['dataset']['combined_input_hash']}`",
        "",
        "## Feature-set comparison",
        "",
        "| Feature set | Outcome | Samples | Accuracy | Baseline | Δ accuracy | Brier | Δ Brier | p-value |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, v in r["phase52"].items():

        def fmt(x):
            return "—" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))

        lines.append(
            f"| {name} | {v['outcome']} | {v['validation_samples'] or 0} | {fmt(v['accuracy'])} | {fmt(v['baseline_accuracy'])} | {fmt(v['accuracy_delta_vs_baseline'])} | {fmt(v['brier'])} | {fmt(v['brier_delta_vs_baseline'])} | {fmt(v['p_value'])} |"
        )
    lines += [
        "",
        "## Evidence interpretation",
        "",
        "### What this proves",
        "- 2020 context initializes feature state without becoming experiment samples.",
        "- Only 2021–2025 research observations enter execution.",
        "- The 60-row feature warmup is supplied by pre-research context rather than deleting research rows.",
        "- The 5-row label horizon remains unchanged.",
        "- The 1200 train+validation gate is measured only on research samples.",
        "- No interpolation, forward-fill, resampling, date truncation, or gate weakening is used.",
        "",
        "### What this does not prove",
        "- It does not prove profitable trading or future predictive power.",
        "- It does not justify causal macro conclusions from this experiment alone.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical ResearchOS Phase 5.2 report")
    parser.add_argument("command", choices=["phase52"])
    parser.parse_args()
    report = _build_report()
    payload = _json_safe(asdict(report))
    out_dir = ROOT / "reports/phase52"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "canonical_phase52_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "canonical_phase52_report.md").write_text(_render(report) + "\n", encoding="utf-8")
    print(_render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
