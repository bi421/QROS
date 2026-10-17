import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from scripts.run_combinatorial_purged_cv import main


def test_cli_writes_reproducibility_manifest_and_split_audit(tmp_path: Path, monkeypatch):
    rows = []
    start = datetime(2024, 1, 1)
    for i in range(120):
        timestamp = start + timedelta(minutes=15 * i)
        z = (i % 11) / 5.0
        aligned = float(i % 2)
        rows.append(
            {
                "event_id": f"event-{i:04d}",
                "timestamp": timestamp.isoformat(),
                "label_end_timestamp": (timestamp + timedelta(minutes=30)).isoformat(),
                "z_speed": z,
                "body_ratio": (i % 7) / 7.0,
                "upper_wick_ratio": (i % 5) / 5.0,
                "lower_wick_ratio": ((i + 2) % 5) / 5.0,
                "h1_aligned": aligned,
                "label": int(z + aligned * 0.7 > 1.0),
            }
        )
    source = tmp_path / "events.json"
    output = tmp_path / "audit.json"
    source.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_combinatorial_purged_cv.py",
            "--input",
            str(source),
            "--output",
            str(output),
            "--groups",
            "4",
            "--test-groups",
            "1",
            "--embargo-minutes",
            "30",
            "--min-train-rows",
            "20",
        ],
    )
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["manifest"]["dataset_sha256"]
    assert report["manifest"]["config_sha256"]
    assert report["manifest"]["source_sha256"]
    assert report["manifest"]["model_source_sha256"]
    assert report["manifest"]["deterministic_result_sha256"]
    assert report["manifest"]["execution_authorized"] is False
    assert report["result"]["requested_split_count"] == 4
    assert len(report["result"]["splits"]) == 4
    assert all("purged_indices_zero_based" in split for split in report["result"]["splits"])
