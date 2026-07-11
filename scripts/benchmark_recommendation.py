#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_AGENT = ROOT / "bin" / "local-agent"


def run_recommendation(
    command: str, num_ctx: int, refresh: bool
) -> tuple[float, dict[str, object]]:
    argv = [
        sys.executable,
        str(LOCAL_AGENT),
        "recommend-model",
        command,
        "--num-ctx",
        str(num_ctx),
        "--json",
    ]
    if refresh:
        argv.append("--refresh")
    started = time.perf_counter()
    completed = subprocess.run(
        argv, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip() or completed.stdout.strip() or "recommendation failed"
        )
    return elapsed_ms, json.loads(completed.stdout)


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((percent / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark warm local-agent model recommendations."
    )
    parser.add_argument("--command", default="review")
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--threshold-ms", type=float)
    args = parser.parse_args()

    if args.runs <= 0:
        raise SystemExit("--runs must be positive")

    run_recommendation(args.command, args.num_ctx, refresh=True)
    timings: list[float] = []
    payloads: list[dict[str, object]] = []
    for _ in range(args.runs):
        elapsed_ms, payload = run_recommendation(args.command, args.num_ctx, refresh=False)
        timings.append(elapsed_ms)
        payloads.append(payload)

    latest = payloads[-1]
    performance = latest.get("performance", {})
    if not isinstance(performance, dict):
        performance = {}
    print(f"runs: {args.runs}")
    print(f"minimum_ms: {min(timings):.1f}")
    print(f"median_ms: {statistics.median(timings):.1f}")
    print(f"p95_ms: {percentile(timings, 95):.1f}")
    print(f"maximum_ms: {max(timings):.1f}")
    print(f"metadata_cache_hits: {performance.get('metadata_cache_hits', 0)}")
    print(f"metadata_cache_misses: {performance.get('metadata_cache_misses', 0)}")
    print(f"show_requests: {performance.get('show_requests', 0)}")
    print("tags_requests_per_run: 1")
    print("ps_requests_per_run: 1")

    if args.threshold_ms is not None and statistics.median(timings) > args.threshold_ms:
        print(
            f"median {statistics.median(timings):.1f} ms exceeded threshold {args.threshold_ms:.1f} ms",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
