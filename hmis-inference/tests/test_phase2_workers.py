"""
Tests for the Phase-2 worker utilities: cache warmer + CRITICAL notifier.

We exercise the pure-Python helpers; the async paths are covered by the
router-test fixture indirectly through the same DB mocks.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def test_warm_interval_default_840():
    """Default warm cadence is 14 minutes (840s), just under the 15-min TTL."""
    import os
    os.environ.pop("INFERENCE_WARM_INTERVAL_SECONDS", None)
    from backend.inference.cache_warmer import warm_interval
    assert warm_interval() == 840


def test_warm_interval_overrides_via_env():
    import os
    os.environ["INFERENCE_WARM_INTERVAL_SECONDS"] = "60"
    try:
        # Reimport to pick up env change.
        import importlib
        import backend.inference.cache_warmer as cw
        importlib.reload(cw)
        assert cw.warm_interval() == 60
    finally:
        os.environ.pop("INFERENCE_WARM_INTERVAL_SECONDS", None)


@pytest.mark.asyncio
async def test_warm_all_invokes_each_workstream():
    """warm_all must call all 4 score functions and write to Redis."""
    from backend.inference import cache_warmer

    with patch.object(cache_warmer.outbreak_risk, "score", new=AsyncMock(return_value=[])), \
         patch.object(cache_warmer.hospital_pressure, "score", new=AsyncMock(return_value=[])), \
         patch.object(cache_warmer.priority_rank, "rank", new=AsyncMock(return_value=[])), \
         patch.object(cache_warmer.policy_memo, "compose", new=AsyncMock(return_value={})), \
         patch.object(cache_warmer.inference_cache, "set_around", new=AsyncMock()) as set_around:
        result = await cache_warmer.warm_all()

    # Four workstreams, four set_around writes.
    assert set_around.await_count == 4
    assert set(result["results"].keys()) == {
        "outbreak_risk", "hospital_pressure", "priority_rank", "policy_memo",
    }


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------
def test_notifier_unconfigured_when_url_missing():
    import importlib
    with patch.dict("os.environ", {"WEBHOOK_URL": "", "WEBHOOK_ENABLED": "1"}, clear=False):
        from backend.inference import notifier
        importlib.reload(notifier)
        assert notifier.is_configured() is False


def test_notifier_unconfigured_when_disabled():
    import importlib
    with patch.dict("os.environ", {"WEBHOOK_URL": "https://example.invalid/", "WEBHOOK_ENABLED": "0"}, clear=False):
        from backend.inference import notifier
        importlib.reload(notifier)
        assert notifier.is_configured() is False


def test_notifier_configured_when_both_set():
    import importlib
    with patch.dict("os.environ", {"WEBHOOK_URL": "https://example.invalid/", "WEBHOOK_ENABLED": "1"}, clear=False):
        from backend.inference import notifier
        importlib.reload(notifier)
        assert notifier.is_configured() is True


def test_snapshots_differ_when_no_prior():
    from backend.inference.notifier import _snapshots_differ
    cur = {"rank": 1, "headline": "ICU emergency at Civil", "severity": "CRITICAL"}
    assert _snapshots_differ(None, cur) is True


def test_snapshots_differ_when_severity_changes():
    from backend.inference.notifier import _snapshots_differ
    prev = {"rank": 1, "headline": "ICU emergency", "severity": "HIGH"}
    cur  = {"rank": 1, "headline": "ICU emergency", "severity": "CRITICAL"}
    assert _snapshots_differ(prev, cur) is True


def test_snapshots_match_when_unchanged():
    from backend.inference.notifier import _snapshots_differ
    snap = {"rank": 1, "headline": "ICU emergency", "severity": "CRITICAL"}
    assert _snapshots_differ(snap, snap) is False


def test_summarise_top_returns_none_when_empty():
    from backend.inference.notifier import _summarise_top
    assert _summarise_top([]) is None
