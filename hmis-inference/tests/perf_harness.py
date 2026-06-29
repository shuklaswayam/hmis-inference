"""Perf benchmark smoke harness — runs in the existing pytest suite.

Set ``PERF_SMOKE=1`` to opt-in. Default behavior: importable module that
the
locustfile (locustfile.py) can also use.

Why not pull in Locust directly? Mid-development envs often don't have
it installed; a 50-line in-process harness is enough to assert the
dashboard stays under 500 ms p95 for the 256-facility steady state.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Optional


@dataclass
class PerfResult:
    name: str
    sample_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    errors: int

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "samples":      self.sample_count,
            "p50_ms":       round(self.p50_ms, 2),
            "p95_ms":       round(self.p95_ms, 2),
            "p99_ms":       round(self.p99_ms, 2),
            "mean_ms":      round(self.mean_ms, 2),
            "errors":       self.errors,
        }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p * len(s))) - 1))
    return s[idx]


async def _run_loop(
    fn: Callable[[], Awaitable],
    *,
    n: int,
    rps: float,
) -> tuple[list[float], int]:
    """Run ``fn`` n times targeting ``rps`` requests/sec.

    Returns ``(latencies_ms, error_count)``.
    """
    interval = 1.0 / max(rps, 0.1)
    latencies: list[float] = []
    errors = 0
    tasks: list[Awaitable] = []

    async def _wrap() -> None:
        nonlocal errors
        t0 = time.perf_counter()
        try:
            await fn()
            latencies.append((time.perf_counter() - t0) * 1000.0)
        except Exception:  # noqa: BLE001
            errors += 1

    for i in range(n):
        tasks.append(asyncio.create_task(_wrap()))
        if i < n - 1:
            await asyncio.sleep(interval)
    await asyncio.gather(*tasks, return_exceptions=False)
    return latencies, errors


def summarise(name: str, latencies: list[float], errors: int) -> PerfResult:
    return PerfResult(
        name=name,
        sample_count=len(latencies),
        p50_ms=_percentile(latencies, 0.50),
        p95_ms=_percentile(latencies, 0.95),
        p99_ms=_percentile(latencies, 0.99),
        mean_ms=statistics.mean(latencies) if latencies else 0.0,
        errors=errors,
    )


async def smoke_run(
    suites: Iterable[tuple[str, Callable[[], Awaitable]]],
    *,
    n: int = 20,
    rps: float = 5.0,
) -> list[PerfResult]:
    """Run the given ``(name, async_callable)`` pairs in sequence.

    Designed for ``pytest --perf-smoke``: cheap and finishes in <2 s.
    """
    results: list[PerfResult] = []
    for name, fn in suites:
        latencies, errors = await _run_loop(fn, n=n, rps=rps)
        results.append(summarise(name, latencies, errors))
    return results


def is_smoke_enabled() -> bool:
    return bool(os.environ.get("PERF_SMOKE", "").strip() == "1")
