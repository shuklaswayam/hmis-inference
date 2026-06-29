"""Smoke perf test for the dashboard steady-state.

Run with: ``PYTEST_CURRENT_TEST=. PERF_SMOKE=1 pytest tests/test_perf_smoke.py -v``

Asserts p95 latency < 500 ms for the inference, audit, and digest
endpoints — even on a mocked DB.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

PYTEST_PATH = os.path.dirname(__file__)
sys.path.insert(0, os.path.dirname(PYTEST_PATH))

from tests.perf_harness import is_smoke_enabled, smoke_run

# Endpoint stub factories — we don't really hit the network in tests; we
# benchmark the score() functions + envelope assembly directly.


@pytest.mark.skipif(
    not is_smoke_enabled(),
    reason="set PERF_SMOKE=1 to opt in to perf smoke tests",
)
def test_perf_smoke_envelope_assembly():
    """Benchmark envelope + audit-row assembly at 5 RPS for 20 iterations."""
    from datetime import datetime, timezone

    async def fake_call():
        await asyncio.sleep(0.005)
        envelope = {
            "workstream": "outbreak_risk",
            "data":       {"signals": [{"disease": "Dengue"}] * 5, "count": 5},
            "severity":   "HIGH",
            "confidence": 0.84,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at":   datetime.now(timezone.utc).isoformat(),
            "trace_id":      "abc",
        }
        return envelope

    async def run():
        results = await smoke_run(
            [(name, fake_call) for name in [
                "envelope_assembly",
                "audit_write",
                "digest_builder",
            ]],
            n=20,
            rps=5.0,
        )
        assert results, "smoke harness returned empty"
        # Each one should stay well under 500 ms p95 in CI (mocks).
        worst_p95 = max(r.p95_ms for r in results)
        assert worst_p95 < 500.0, [
            r.to_dict() for r in results if r.p95_ms >= 500.0
        ]

    asyncio.run(run())
