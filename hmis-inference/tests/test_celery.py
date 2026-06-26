"""
Unit tests for HMIS Celery tasks.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def test_celery_app_created():
    """Celery app should be created with correct config."""
    from backend.tasks import app
    assert app.main == "hmis_tasks"
    assert app.conf.broker_url == "redis://localhost:6379/0"


def test_beat_schedule_configured():
    """Beat schedule should have nightly-inference task."""
    from backend.tasks import app
    beat = app.conf.beat_schedule
    assert "nightly-inference" in beat
    task = beat["nightly-inference"]
    assert task["task"] == "tasks.run_nightly_inference"
    # Verify crontab runs at 00:30
    schedule = task["schedule"]
    assert 0 in schedule.hour
    assert 30 in schedule.minute


def test_task_registered():
    """run_nightly_inference task should be registered."""
    from backend.tasks import app
    registered = app.tasks.keys()
    assert "tasks.run_nightly_inference" in registered
