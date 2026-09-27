"""Run the complete Phase 5.2 five-way comparison and emit audit evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from researchos.experiments.phase52 import FEATURE_SET_NAMES, Phase52Config, run_phase52_comparison
from researchos.experiments.phase52.scripts.run_phase52_experiment import (
    _build_common_observation_sample,
    _load_candles,
    _load_macro_series,
)

REQUIRED = (("XAUUSD", "csv"), ("DXY", "dxy"), ("US10Y", "us10y"), ("VIX", "vix"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_repository_commit(value: str) -> str:
    if len(value) != 40 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError("repository_commit must be an exact 40-character Git SHA")
    return value


def _date_key(value: object) -> str:
    return str(value)[:10]


def _metric(result: dict, section: str, key: str, default: object = None) -> object:
    value = result.get(section)
    if not isinstance(value, dict):
        return default
    return value.get(key, default)


def _fmt_float(value: object, digits: int = 6) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_p(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return "—"


def _validate_holdout_results(results: dict[str, object], holdout_size: int) -> None:
    if holdout_size <= 0:
        raise ValueError("holdout_size must be positive")
    for feature_set in FEATURE_SET_NAMES:
        result = results.get(feature_set)
        if not isinstance(result, dict):
            raise ValueError(f"{feature_set}: missing result payload")
        metadata = result.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError(f"{feature_set}: missing result metadata")
        holdout = metadata.get("holdout")
        if not isinstance(holdout, dict):
            raise ValueError(f"{feature_set}: final holdout artifact is missing")
        if holdout.get("holdout_events") != holdout_size:
            raise ValueError(f"{feature_set}: holdout event count does not match configured holdout_size")
        predictions = holdout.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != holdout_size:
            raise ValueError(f"{feature_set}: holdout prediction count does not match holdout_size")
        if holdout.get("holdout_used_for_selection") is not False:
            raise ValueError(f"{feature_set}: holdout selection exclusion contract is invalid")
        if holdout.get("fit_is_pre_holdout_only") is not True:
            raise ValueError(f"{feature_set}: holdout fit is not marked pre-holdout only")
        temporal = metadata.get("temporal_contract")
        if not isinstance(temporal, dict) or temporal.get("holdout_excluded_from_wfo_aggregate") is not True:
            raise ValueError(f"{feature_set}: holdout/WFO temporal exclusion contract is missing")
        calibration = metadata.get("calibration_contract")
        if not isinstance(calibration, dict) or calibration.get("holdout_excluded") is not True:
            raise ValueError(f"{feature_set}: holdout calibration exclusion contract is missing")


def _write_report(path: Path, payload: dict) -> None:
    lines = [
        "# ResearchOS Phase 5.2 — Five-Way Empirical Evidence",
        "",
        f"- Repository commit: `{payload['repository_commit']}`",
        f"- Common observations: **{payload['common_sample']['count']}**",
        f"- First common timestamp: `{payload['common_sample']['first']}`",
        f"- Last common timestamp: `{payload['common_sample']['last']}`",
        f"- DXY source: `{payload['sources']['DXY']['identity']}`",
        "- DXY ICE benchmark equivalence: **NOT PROVEN**",
        "",
        "## Feature-set results",
        "",
        "| Feature set | Outcome | OOS n | Accuracy | Brier | Net accuracy | p-value | Significant |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    price_result = payload["results"].get("PRICE_ONLY", {})
    price_accuracy = _metric(price_result, "model", "accuracy")
    price_brier = _metric(price_result, "model", "brier_score")
    price_net_accuracy = _metric(price_result, "cost", "net_accuracy_all")
    for name in FEATURE_SET_NAMES:
        result = payload["results"].get(name, {})
        model = result.get("model") if isinstance(result.get("model"), dict) else None
        cost = result.get("cost") if isinstance(result.get("cost"), dict) else None
        sig = result.get("significance") if isinstance(result.get("significance"), dict) else None
        outcome = result.get("outcome", "UNKNOWN")
        model_n = model.get("sample_count") if model else None
        accuracy = model.get("accuracy") if model else None
        brier = model.get("brier_score") if model else None
        net_accuracy = cost.get("net_accuracy_all") if cost else None
        p_value = sig.get("p_value") if sig else None
        significant = sig.get("significant") if sig else None
        lines.append(
            f"| {name} | {outcome} | {model_n if model_n is not None else '—'} | "
            f"{_fmt_float(accuracy)} | {_fmt_float(brier)} | "
            f"{_fmt_float(net_accuracy)} | {_fmt_p(p_value)} | "
            f"{significant if significant is not None else '—'} |"
        )
    lines += [
        "",
        "## Baseline deltas",
        "",
        "| Feature set | Accuracy delta vs PRICE_ONLY | Brier delta vs PRICE_ONLY | Net accuracy delta vs PRICE_ONLY |",
        "|---|---:|---:|---:|",
    ]
    for name in FEATURE_SET_NAMES:
        result = payload["results"].get(name, {})
        accuracy = _metric(result, "model", "accuracy")
        brier = _metric(result, "model", "brier_score")
        net_accuracy = _metric(result, "cost", "net_accuracy_all")
        def delta(value: object, baseline: object) -> str:
            if value is None or baseline is None:
                return "—"
            try:
                return f"{float(value) - float(baseline):+.6f}"
            except (TypeError, ValueError):
                return "—"
        lines.append(
            f"| {name} | {delta(accuracy, price_accuracy)} | "
            f"{delta(brier, price_brier)} | {delta(net_accuracy, price_net_accuracy)} |"
        )
    lines += [
        "",
        "## Final independent holdout",
        "",
        "| Feature set | Holdout n | Holdout start | Holdout end | Accuracy | Brier | p-value | Accuracy-delta 95% CI |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ]
    for name in FEATURE_SET_NAMES:
        metadata = payload["results"].get(name, {}).get("metadata", {})
        holdout = metadata.get("holdout", {}) if isinstance(metadata, dict) else {}
        model = holdout.get("model", {}) if isinstance(holdout, dict) else {}
        sig = holdout.get("significance", {}) if isinstance(holdout, dict) else {}
        ci = holdout.get("accuracy_delta_ci_95", {}) if isinstance(holdout, dict) else {}
        lines.append(
            f"| {name} | {holdout.get('holdout_events', '—')} | "
            f"{holdout.get('start', '—')} | {holdout.get('end', '—')} | "
            f"{_fmt_float(model.get('accuracy') if isinstance(model, dict) else None)} | "
            f"{_fmt_float(model.get('brier_score') if isinstance(model, dict) else None)} | "
            f"{_fmt_p(sig.get('p_value') if isinstance(sig, dict) else None)} | "
            f"[{_fmt_float(ci.get('lower') if isinstance(ci, dict) else None)}, "
            f"{_fmt_float(ci.get('upper') if isinstance(ci, dict) else None)}] |"
        )

    lines += [
        "",
        "## Scientific boundary",
        "",
        "This artifact is evidence for the configured ResearchOS experiment and its explicit data sources. It is not evidence of live trading profitability or an investable edge.",
        "The DXY input is the Dukascopy `dollaridxusd` series; equivalence to the official ICE DXY benchmark has not been independently established. Any conclusion must therefore be stated as a result conditioned on this secondary DXY source, not as a claim about ICE DXY.",
        "",
        f"Reproducibility hashes: `{json.dumps(payload['reproducibility_hashes'], sort_keys=True)}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run complete Phase 5.2 evidence package")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--dxy", required=True)
    parser.add_argument("--us10y", required=True)
    parser.add_argument("--vix", required=True)
    parser.add_argument("--format", default="auto", choices=["mt5", "tradingview", "auto"])
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--train", type=int, default=1000)
    parser.add_argument("--valid", type=int, default=200)
    parser.add_argument("--step", type=int, default=200)
    parser.add_argument("--holdout", type=int, default=40)
    parser.add_argument("--neighbors", type=int, default=25)
    parser.add_argument("--spread", default="fixed:0.0")
    parser.add_argument("--slippage", default="fixed:0.0")
    parser.add_argument("--commission", default="fixed:0.0")
    parser.add_argument("--out-dir", default="reports/phase52")
    parser.add_argument(
        "--repository-commit",
        required=True,
        help="Exact 40-character Git commit SHA for the code used to generate this evidence",
    )
    args = parser.parse_args(argv)
    repository_commit = _validate_repository_commit(args.repository_commit)

    paths = {"XAUUSD": Path(args.csv), "DXY": Path(args.dxy), "US10Y": Path(args.us10y), "VIX": Path(args.vix)}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        print(f"BLOCKED: missing required real-data files: {', '.join(missing)}")
        return 2

    close, high, low, volume, timestamps = _load_candles(args.csv, args.format, args.symbol, args.timeframe)
    macro, macro_timestamps = {}, {}
    for symbol, path in (("DXY", args.dxy), ("US10Y", args.us10y), ("VIX", args.vix)):
        values, factor_timestamps = _load_macro_series(path, args.format, symbol, args.timeframe)
        macro[symbol], macro_timestamps[symbol] = values, factor_timestamps

    original_counts = {"XAUUSD": len(timestamps), **{symbol: len(macro_timestamps[symbol]) for symbol in macro_timestamps}}
    close, high, low, volume, common_ts, macro, macro_timestamps = _build_common_observation_sample(close, high, low, volume, timestamps, macro, macro_timestamps, ("DXY", "US10Y", "VIX"))
    if len(common_ts) < args.train + args.valid:
        print(f"BLOCKED: common sample has {len(common_ts)} rows; requires at least {args.train + args.valid}")
        return 2

    cfg = Phase52Config(symbol=args.symbol, timeframe=args.timeframe, horizon=args.horizon, threshold=args.threshold, train_size=args.train, validation_size=args.valid, step_size=args.step, holdout_size=args.holdout, n_neighbors=args.neighbors, spread_spec=args.spread, slippage_spec=args.slippage, commission_spec=args.commission)
    results = run_phase52_comparison(close, high, low, volume, macro, config=cfg, timestamps=common_ts, macro_timestamps=macro_timestamps)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_dict = {name: result.to_dict() for name, result in results.items()}
    _validate_holdout_results(result_dict, args.holdout)
    configuration = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "horizon": args.horizon,
        "threshold": args.threshold,
        "train_size": args.train,
        "validation_size": args.valid,
        "step_size": args.step,
        "holdout_size": args.holdout,
        "neighbors": args.neighbors,
        "spread": args.spread,
        "slippage": args.slippage,
        "commission": args.commission,
    }
    configuration_hash = hashlib.sha256(
        json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload = {
        "schema": "researchos/phase52/evidence/v3",
        "repository_commit": repository_commit,
        "configuration": configuration,
        "configuration_hash": configuration_hash,
        "feature_set_scope": list(FEATURE_SET_NAMES),
        "sources": {
            "XAUUSD": {"path": str(paths["XAUUSD"]), "sha256": _sha256(paths["XAUUSD"]), "rows": original_counts["XAUUSD"]},
            "DXY": {"path": str(paths["DXY"]), "sha256": _sha256(paths["DXY"]), "rows": original_counts["DXY"], "identity": "Dukascopy dollaridxusd; secondary DXY series"},
            "US10Y": {"path": str(paths["US10Y"]), "sha256": _sha256(paths["US10Y"]), "rows": original_counts["US10Y"], "identity": "FRED DGS10"},
            "VIX": {"path": str(paths["VIX"]), "sha256": _sha256(paths["VIX"]), "rows": original_counts["VIX"], "identity": "FRED VIXCLS"},
        },
        "common_sample": {
            "count": len(common_ts),
            "first": _date_key(common_ts[0]),
            "last": _date_key(common_ts[-1]),
            "dropped_from_xauusd": original_counts["XAUUSD"] - len(common_ts),
            "timestamps_sha256": hashlib.sha256(json.dumps([str(x) for x in common_ts], separators=(",", ":")).encode()).hexdigest(),
        },
        "holdout_contract": {
            "holdout_size": args.holdout,
            "wfo_aggregate_excludes_holdout": True,
            "selection_excludes_holdout": True,
            "calibration_excludes_holdout": True,
        },
        "results": result_dict,
        "reproducibility_hashes": {name: result.reproducibility_hash for name, result in results.items()},
    }
    json_path = out_dir / "phase52_evidence.json"
    md_path = out_dir / "phase52_evidence.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(md_path, payload)

    print("=" * 100)
    print("PHASE 5.2 COMPLETE EVIDENCE PACKAGE")
    print(f"COMMON SAMPLE : {len(common_ts)}")
    print(f"FIRST / LAST  : {_date_key(common_ts[0])} / {_date_key(common_ts[-1])}")
    for name in FEATURE_SET_NAMES:
        result = results[name]
        model = result.model.to_dict() if result.model else None
        sig = result.significance.to_dict() if result.significance else None
        print(f"{name:18} | {result.outcome:10} | folds={result.num_folds:3d} | accuracy={_fmt_float(model.get('accuracy') if model else None)} | brier={_fmt_float(model.get('brier_score') if model else None)} | p={_fmt_p(sig.get('p_value') if sig else None)}")
    print(f"JSON            : {json_path}")
    print(f"REPORT          : {md_path}")
    print("DXY BOUNDARY    : Dukascopy secondary series; ICE equivalence NOT PROVEN")
    print("=" * 100)
    return 0 if all(result.outcome != "BLOCKED" for result in results.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
