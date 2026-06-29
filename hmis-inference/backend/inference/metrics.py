"""Analytics + counters for the inference system.

Phase 5 — production observability:

* Counters kept simple (per-workstream call counts, cache hit/miss,
  alert kinds).
* Histograms implemented in pure stdlib (no ``prometheus_client``
  dependency). Each histogram stores count / sum / bucketed counts;
  ``to_prometheus_text()`` emits ``inf_durations_seconds_bucket``
  quantised to Prometheus-style buckets so a stable scrape format
  is preserved whether or not the optional dependency is installed.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bucketed histograms
# ---------------------------------------------------------------------------
_BUCKET_BOUNDS_MS = (1, 2.5, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10_000, 30_000)

# Latency buckets are stored in seconds for Prometheus-text compatibility,
# even though the lock-step sides measure in ms.
_HIST_BUCKETS_S = tuple(b / 1000.0 for b in _BUCKET_BOUNDS_MS) + (math.inf,)

_lock = threading.RLock()


class _LatencyHistogram:
    def __init__(self) -> None:
        # buckets[i] = count of observations falling inside bucket i.
        # Last bucket is +Inf.
        self.buckets: list[int] = [0] * len(_HIST_BUCKETS_S)
        self.count: int = 0
        self.sum: float = 0.0
        # Streaming quantile reservoir — bounded to 512 samples for memory.
        self._reservoir: list[float] = []

    def observe(self, seconds: float) -> None:
        with _lock:
            self.count += 1
            self.sum += seconds
            for i, b in enumerate(_HIST_BUCKETS_S):
                if seconds <= b:
                    self.buckets[i] += 1
            self._reservoir.append(seconds)
            if len(self._reservoir) > 512:
                # Simple down-sample: drop every other entry.
                self._reservoir = self._reservoir[::2]

    def quantile(self, q: float) -> float:
        with _lock:
            if not self._reservoir:
                return 0.0
            s = sorted(self._reservoir)
            idx = max(0, min(len(s) - 1, int(round(q * len(s))) - 1))
            return s[idx]

    def to_prometheus(self, workstream: str) -> list[str]:
        out: list[str] = []
        cum = 0
        with _lock:
            for i, b in enumerate(_HIST_BUCKETS_S[:-1]):  # skip +Inf tail
                cum = self.buckets[i]
                le = "+Inf" if math.isinf(b) else f"{b:.3f}"
                out.append(f'inf_durations_seconds_bucket{{workstream="{workstream}",le="{le}"}} {cum}')
            out.append(f'inf_durations_seconds_count{{workstream="{workstream}"}} {self.count}')
            out.append(f'inf_durations_seconds_sum{{workstream="{workstream}"}} {self.sum:.3f}')
        return out


# ---------------------------------------------------------------------------
# Counter stores
# ---------------------------------------------------------------------------
_call_counts: dict[tuple[str, str], int] = {}
_cache_counts: dict[tuple[str, str], int] = {}
_alert_counts: dict[str, int] = {}
_durations: dict[str, _LatencyHistogram] = {}


def _histogram_for(workstream: str) -> _LatencyHistogram:
    if workstream not in _durations:
        _durations[workstream] = _LatencyHistogram()
    return _durations[workstream]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def record_call(workstream: str, *, status: str = "ok", seconds: float = 0.0) -> None:
    with _lock:
        _call_counts[(workstream, status)] = _call_counts.get((workstream, status), 0) + 1
        if seconds > 0:
            _histogram_for(workstream).observe(seconds)


def record_cache(workstream: str, *, hit: bool) -> None:
    kind = "hit" if hit else "miss"
    with _lock:
        _cache_counts[(workstream, kind)] = _cache_counts.get((workstream, kind), 0) + 1


def record_alert(kind: str, *, count: int = 1) -> None:
    valid = {"critical_transition", "webhook_fired", "webhook_skipped"}
    if kind not in valid:
        return
    with _lock:
        _alert_counts[kind] = _alert_counts.get(kind, 0) + count


@contextmanager
def track_call(workstream: str) -> Iterator[dict]:
    meta = {"status": "ok"}
    t0 = time.perf_counter()
    try:
        yield meta
    except Exception:
        meta["status"] = "error"
        raise
    finally:
        elapsed = time.perf_counter() - t0
        record_call(workstream, status=meta["status"], seconds=elapsed)


class async_track_call:
    def __init__(self, workstream: str) -> None:
        self.workstream = workstream
        self.meta = {"status": "ok"}
        self._t0 = 0.0

    async def __aenter__(self) -> dict:
        self._t0 = time.perf_counter()
        return self.meta

    async def __aexit__(self, exc_type, exc, tb):
        elapsed = time.perf_counter() - self._t0
        status = "ok" if exc_type is None else "error"
        record_call(self.workstream, status=status, seconds=elapsed)
        return False


def histogram_for(workstream: str) -> _LatencyHistogram:
    return _histogram_for(workstream)


def quantile(workstream: str, q: float) -> float:
    return _histogram_for(workstream).quantile(q)


def to_prometheus_text() -> str:
    """Render Prometheus-style text exposition."""
    lines: list[str] = []
    lines.append("# HELP inf_calls_total Total inference calls by workstream and status.")
    lines.append("# TYPE inf_calls_total counter")
    with _lock:
        for (ws, status), value in sorted(_call_counts.items()):
            lines.append(f'inf_calls_total{{workstream="{ws}",status="{status}"}} {value}')
        lines.append("# HELP inf_cache_total Cache hit/miss counts by workstream.")
        lines.append("# TYPE inf_cache_total counter")
        for (ws, kind), value in sorted(_cache_counts.items()):
            lines.append(f'inf_cache_total{{workstream="{ws}",kind="{kind}"}} {value}')
        lines.append("# HELP inf_alerts_total Outbound alert events.")
        lines.append("# TYPE inf_alerts_total counter")
        for kind, value in sorted(_alert_counts.items()):
            lines.append(f'inf_alerts_total{{kind="{kind}"}} {value}')
        lines.append("# HELP inf_uptime_seconds Time since first inference request.")
        lines.append("# TYPE inf_uptime_seconds gauge")
        lines.append(f"inf_uptime_seconds 0")
        lines.append("# HELP inf_durations_seconds Workstream compute-time histogram.")
        lines.append("# TYPE inf_durations_seconds histogram")
        for ws in sorted(_durations):
            lines.extend(_durations[ws].to_prometheus(ws))
    return "\n".join(lines) + "\n"


def reset() -> None:  # pragma: no cover — test helper
    with _lock:
        _call_counts.clear()
        _cache_counts.clear()
        _alert_counts.clear()
        _durations.clear()
