#!/usr/bin/env python3
"""Dependency-free authenticated HTTP load gate for a deployed QROS environment."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request


def request_once(url: str, token: str | None, timeout: float) -> tuple[float, int, str | None]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return (time.perf_counter() - started) * 1000.0, response.status, None
    except urllib.error.HTTPError as exc:
        return (time.perf_counter() - started) * 1000.0, exc.code, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return (time.perf_counter() - started) * 1000.0, 0, type(exc).__name__


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", default="/v1/me")
    parser.add_argument("--token", default="")
    parser.add_argument("--token-env", default="QROS_JWT")
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=1000.0)
    args = parser.parse_args()

    if args.duration_seconds <= 0 or args.concurrency <= 0:
        parser.error("duration-seconds and concurrency must be positive")

    token = args.token or __import__("os").environ.get(args.token_env, "")
    url = args.base_url.rstrip("/") + "/" + args.path.lstrip("/")
    deadline = time.monotonic() + args.duration_seconds
    results: list[tuple[float, int, str | None]] = []

    def worker() -> list[tuple[float, int, str | None]]:
        local: list[tuple[float, int, str | None]] = []
        while time.monotonic() < deadline:
            local.append(request_once(url, token or None, args.timeout_seconds))
        return local

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(args.concurrency)]
        for future in futures:
            results.extend(future.result())
    elapsed = time.perf_counter() - started

    latencies = [item[0] for item in results]
    successes = sum(200 <= item[1] < 300 for item in results)
    failures = len(results) - successes
    error_rate = failures / len(results) if results else 1.0
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)

    summary = {
        "url": url,
        "duration_seconds": round(elapsed, 3),
        "concurrency": args.concurrency,
        "requests": len(results),
        "successes": successes,
        "failures": failures,
        "error_rate": round(error_rate, 6),
        "requests_per_second": round(len(results) / elapsed, 3) if elapsed else 0.0,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else None,
            "mean": round(statistics.fmean(latencies), 2) if latencies else None,
            "p50": round(p50, 2) if latencies else None,
            "p95": round(p95, 2) if latencies else None,
            "p99": round(p99, 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
        "thresholds": {
            "max_error_rate": args.max_error_rate,
            "max_p95_ms": args.max_p95_ms,
        },
    }
    print(json.dumps(summary, indent=2))

    if not results or error_rate > args.max_error_rate or p95 > args.max_p95_ms:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
