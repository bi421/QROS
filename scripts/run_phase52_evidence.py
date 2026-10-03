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
            raise ValueError(
                f"{feature_set}: holdout event count does not match configured holdout_size"
            )
        predictions = holdout.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != holdout_size:
            raise ValueError(f"{feature_set}: holdout prediction count does not match holdout_size")
        if holdout.get("holdout_used_for_selection") is not False:
            raise ValueError(f"{feature_set}: holdout selection exclusion contract is invalid")
        if holdout.get("fit_is_pre_holdout_only") is not True:
            raise ValueError(f"{feature_set}: holdout fit is not marked pre-holdout only")
        temporal = metadata.get("temporal_contract")
        if (
            not isinstance(temporal, dict)
            or temporal.get("holdout_excluded_from_wfo_aggregate") is not True
        ):
            raise ValueError(f"{feature_set}: holdout/WFO temporal exclusion contract is missing")
        calibration = metadata.get("calibration_contract")
        if not isinstance(calibration, dict) or calibration.get("holdout_excluded") is not True:
            raise ValueError(f"{feature_set}: holdout calibration exclusion contract is missing")


def _build_blocked_payload(
    *,
    repository_commit: str,
    configuration: dict[str, object],
    paths: dict[str, Path],
    original_counts: dict[str, int],
    common_ts: list[object],
    results: dict[str, dict[str, object]],
    blocking_stage: str,
    blocking_reason: str,
    actual_prepared_samples: int | None = None,
) -> dict[str, object]:
    configuration_hash = hashlib.sha256(
        json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    blocked_results = {}
    for feature_set in FEATURE_SET_NAMES:
        result = results.get(feature_set)
        if not isinstance(result, dict):
            result = {"outcome": "BLOCKED", "metadata": {"blocked_reason": blocking_reason}}
        blocked_results[feature_set] = result
    return {
        "schema": "researchos/phase52/evidence/v3",
        "repository_commit": repository_commit,
        "execution_status": "BLOCKED",
        "blocking": {
            "stage": blocking_stage,
            "reason": blocking_reason,
            "holdout_scoring_executed": False,
        },
        "configuration": configuration,
        "configuration_hash": configuration_hash,
        "sample_requirements": {
            "required_prepared_samples": (
                configuration["train_size"]
                + configuration["validation_size"]
                + configuration["holdout_size"]
                + configuration["horizon"]
            ),
            "actual_prepared_samples": actual_prepared_samples,
            "common_observations": len(common_ts),
        },
        "feature_set_scope": list(FEATURE_SET_NAMES),
        "sources": {
            "XAUUSD": {
                "path": str(paths["XAUUSD"]),
                "sha256": _sha256(paths["XAUUSD"]),
                "rows": original_counts["XAUUSD"],
                "identity": "XAUUSD 2021-2025 research series",
            },
            "DXY": {
                "path": str(paths["DXY"]),
                "sha256": _sha256(paths["DXY"]),
                "rows": original_counts["DXY"],
                "identity": "Dukascopy dollaridxusd; secondary DXY series",
            },
            "US10Y": {
                "path": str(paths["US10Y"]),
                "sha256": _sha256(paths["US10Y"]),
                "rows": original_counts["US10Y"],
                "identity": "FRED DGS10",
            },
            "VIX": {
                "path": str(paths["VIX"]),
                "sha256": _sha256(paths["VIX"]),
                "rows": original_counts["VIX"],
                "identity": "FRED VIXCLS",
            },
        },
        "common_sample": {
            "count": len(common_ts),
            "first": _date_key(common_ts[0]) if common_ts else None,
            "last": _date_key(common_ts[-1]) if common_ts else None,
            "dropped_from_xauusd": original_counts["XAUUSD"] - len(common_ts),
            "timestamps_sha256": hashlib.sha256(
                json.dumps([str(x) for x in common_ts], separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "holdout_contract": {
            "holdout_size": configuration["holdout_size"],
            "wfo_aggregate_excludes_holdout": True,
            "selection_excludes_holdout": True,
            "calibration_excludes_holdout": True,
            "predictions_present": False,
            "metrics_present": False,
        },
        "results": blocked_results,
        "reproducibility_hashes": {
            name: result.get("reproducibility_hash")
            for name, result in blocked_results.items()
            if result.get("reproducibility_hash")
        },
        "dxy_provenance": {
            "provider": "Dukascopy",
            "instrument": "dollaridxusd",
            "source_type": "secondary",
            "ice_dxy_equivalence": "NOT PROVEN",
        },
    }


def _write_report(path: Path, payload: dict) -> None:
    if payload.get("execution_status") == "BLOCKED":
        blocking = payload.get("blocking", {})
        requirements = payload.get("sample_requirements", {})
        lines = [
            "# ResearchOS Phase 5.2 — Blocked Evidence",
            "",
            f"- Repository commit: {payload['repository_commit']}",
            "- Execution status: **BLOCKED**",
            f"- Blocking stage: **{blocking.get('stage', 'UNKNOWN') if isinstance(blocking, dict) else 'UNKNOWN'}**",
            f"- Blocking reason: {blocking.get('reason', 'MISSING') if isinstance(blocking, dict) else 'MISSING'}",
            f"- Common observations: **{payload['common_sample']['count']}**",
            f"- Required prepared observations: **{requirements.get('required_prepared_samples', '—') if isinstance(requirements, dict) else '—'}**",
            f"- Actual prepared observations: **{requirements.get('actual_prepared_samples', '—') if isinstance(requirements, dict) else '—'}**",
            "- Final holdout scoring: **NOT EXECUTED**",
            "- Holdout predictions: **ABSENT**",
            "- Holdout metrics: **ABSENT**",
            "",
            "No numerical holdout result was generated because the governed execution was blocked.",
            "DXY source: Dukascopy dollaridxusd; ICE benchmark equivalence: **NOT PROVEN**.",
            "",
        ]
        for name in FEATURE_SET_NAMES:
            result = payload["results"].get(name, {})
            lines.append(f"- {name}: **{result.get('outcome', 'BLOCKED')}**")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

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

    paths = {
        "XAUUSD": Path(args.csv),
        "DXY": Path(args.dxy),
        "US10Y": Path(args.us10y),
        "VIX": Path(args.vix),
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        print(f"BLOCKED: missing required real-data files: {', '.join(missing)}")
        return 2

    close, high, low, volume, timestamps = _load_candles(
        args.csv, args.format, args.symbol, args.timeframe
    )
    macro, macro_timestamps = {}, {}
    for symbol, path in (("DXY", args.dxy), ("US10Y", args.us10y), ("VIX", args.vix)):
        values, factor_timestamps = _load_macro_series(path, args.format, symbol, args.timeframe)
        macro[symbol], macro_timestamps[symbol] = values, factor_timestamps

    original_counts = {
        "XAUUSD": len(timestamps),
        **{symbol: len(macro_timestamps[symbol]) for symbol in macro_timestamps},
    }
    close, high, low, volume, common_ts, macro, macro_timestamps = _build_common_observation_sample(
        close,
        high,
        low,
        volume,
        timestamps,
        macro,
        macro_timestamps,
        ("DXY", "US10Y", "VIX"),
    )
    required_common_rows = args.train + args.valid + args.holdout + args.horizon

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

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if len(common_ts) < required_common_rows:
        blocking_reason = (
            f"common sample has {len(common_ts)} rows; "
            f"requires at least {required_common_rows} for walk-forward plus final holdout"
        )
        payload = _build_blocked_payload(
            repository_commit=repository_commit,
            configuration=configuration,
            paths=paths,
            original_counts=original_counts,
            common_ts=list(common_ts),
            results={
                name: {
                    "outcome": "BLOCKED",
                    "metadata": {
                        "feature_set": name,
                        "blocked_reason": blocking_reason,
                        "holdout_predictions_present": False,
                        "holdout_metrics_present": False,
                    },
                }
                for name in FEATURE_SET_NAMES
            },
            blocking_stage="common_sample_gate",
            blocking_reason=blocking_reason,
        )
        results = None
    else:
        cfg = Phase52Config(
            symbol=args.symbol,
            timeframe=args.timeframe,
            horizon=args.horizon,
            threshold=args.threshold,
            train_size=args.train,
            validation_size=args.valid,
            step_size=args.step,
            holdout_size=args.holdout,
            n_neighbors=args.neighbors,
            spread_spec=args.spread,
            slippage_spec=args.slippage,
            commission_spec=args.commission,
        )
        results = run_phase52_comparison(
            close,
            high,
            low,
            volume,
            macro,
            config=cfg,
            timestamps=common_ts,
            macro_timestamps=macro_timestamps,
        )
        result_dict = {name: result.to_dict() for name, result in results.items()}
        if any(result.get("outcome") == "BLOCKED" for result in result_dict.values()):
            blocked_reasons = [
                str(result.get("metadata", {}).get("blocked_reason", ""))
                for result in result_dict.values()
                if result.get("outcome") == "BLOCKED"
            ]
            payload = _build_blocked_payload(
                repository_commit=repository_commit,
                configuration=configuration,
                paths=paths,
                original_counts=original_counts,
                common_ts=list(common_ts),
                results=result_dict,
                blocking_stage="prepared_execution_gate",
                actual_prepared_samples=next(
                    (
                        result.get("metadata", {}).get("actual_prepared_samples")
                        for result in result_dict.values()
                        if result.get("outcome") == "BLOCKED"
                        and isinstance(result.get("metadata"), dict)
                        and result.get("metadata", {}).get("actual_prepared_samples") is not None
                    ),
                    None,
                ),
                blocking_reason=blocked_reasons[0]
                if blocked_reasons
                else "Phase 5.2 execution returned BLOCKED",
            )
        else:
            _validate_holdout_results(result_dict, args.holdout)
            payload = {
                "schema": "researchos/phase52/evidence/v3",
                "repository_commit": repository_commit,
                "execution_status": "EXECUTED",
                "configuration": configuration,
                "configuration_hash": hashlib.sha256(
                    json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "feature_set_scope": list(FEATURE_SET_NAMES),
                "sources": {
                    "XAUUSD": {
                        "path": str(paths["XAUUSD"]),
                        "sha256": _sha256(paths["XAUUSD"]),
                        "rows": original_counts["XAUUSD"],
                    },
                    "DXY": {
                        "path": str(paths["DXY"]),
                        "sha256": _sha256(paths["DXY"]),
                        "rows": original_counts["DXY"],
                        "identity": "Dukascopy dollaridxusd; secondary DXY series",
                    },
                    "US10Y": {
                        "path": str(paths["US10Y"]),
                        "sha256": _sha256(paths["US10Y"]),
                        "rows": original_counts["US10Y"],
                        "identity": "FRED DGS10",
                    },
                    "VIX": {
                        "path": str(paths["VIX"]),
                        "sha256": _sha256(paths["VIX"]),
                        "rows": original_counts["VIX"],
                        "identity": "FRED VIXCLS",
                    },
                },
                "common_sample": {
                    "count": len(common_ts),
                    "first": _date_key(common_ts[0]),
                    "last": _date_key(common_ts[-1]),
                    "dropped_from_xauusd": original_counts["XAUUSD"] - len(common_ts),
                    "timestamps_sha256": hashlib.sha256(
                        json.dumps([str(x) for x in common_ts], separators=(",", ":")).encode()
                    ).hexdigest(),
                },
                "holdout_contract": {
                    "holdout_size": args.holdout,
                    "wfo_aggregate_excludes_holdout": True,
                    "selection_excludes_holdout": True,
                    "calibration_excludes_holdout": True,
                },
                "results": result_dict,
                "reproducibility_hashes": {
                    name: result.reproducibility_hash for name, result in results.items()
                },
                "dxy_provenance": {
                    "provider": "Dukascopy",
                    "instrument": "dollaridxusd",
                    "source_type": "secondary",
                    "ice_dxy_equivalence": "NOT PROVEN",
                },
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
        result_payload = payload["results"][name]
        if payload.get("execution_status") == "EXECUTED":
            model = (
                result_payload.get("model")
                if isinstance(result_payload.get("model"), dict)
                else None
            )
            sig = (
                result_payload.get("significance")
                if isinstance(result_payload.get("significance"), dict)
                else None
            )
            folds = result_payload.get("num_folds", 0)
            print(
                f"{name:18} | {result_payload.get('outcome', 'UNKNOWN'):10} | "
                f"folds={folds:3d} | accuracy={_fmt_float(model.get('accuracy') if model else None)} | "
                f"brier={_fmt_float(model.get('brier_score') if model else None)} | "
                f"p={_fmt_p(sig.get('p_value') if sig else None)}"
            )
        else:
            print(f"{name:18} | BLOCKED    | folds=  0 | accuracy=— | brier=— | p=—")
    print(f"JSON            : {json_path}")
    print(f"REPORT          : {md_path}")
    print("DXY BOUNDARY    : Dukascopy secondary series; ICE equivalence NOT PROVEN")
    print("=" * 100)
    return 0 if payload.get("execution_status") == "EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
