"""
Celery tasks — configuration + task registration + beat schedule sanity.

Heavy inference work touched by the nightly task is the integrated end-to-end
path covered by the live integration suite; these tests pin down the contract
the worker needs to honour without spinning up Postgres + Redis.
"""
import pytest

from backend.tasks import app, run_nightly_inference


# ─────────────────────────────────────────────────────────────────────────────
# Celery app wiring
# ─────────────────────────────────────────────────────────────────────────────
class TestCeleryConfig:
    def test_app_name(self):
        assert app.main == "hmis_tasks"

    def test_broker_and_backend_both_redis(self):
        """Single Redis for both broker and result backend keeps container
        count to one — verify the contract is intact."""
        assert "redis" in app.conf.broker_url
        assert "redis" in app.conf.result_backend

    def test_timezone_set_to_kolkata(self):
        """IST — the workers live in the same TZ as the data they process."""
        assert app.conf.timezone == "Asia/Kolkata"
        assert app.conf.enable_utc is True

    def test_json_serialisation_only(self):
        """Restrict accept_content to JSON — tighter security surface."""
        assert app.conf.task_serializer == "json"
        assert app.conf.result_serializer == "json"
        assert "json" in app.conf.accept_content

    def test_beat_schedule_includes_nightly_inference(self):
        """Nightly inference task is scheduled at 00:30 IST — pin the schedule
        so a silent config drift doesn't disable the daily run."""
        assert "nightly-inference" in app.conf.beat_schedule
        sched = app.conf.beat_schedule["nightly-inference"]
        assert sched["task"] == "tasks.run_nightly_inference"
        # 00:30 IST via crontab(hour=0, minute=30)
        assert sched["schedule"].hour == 0
        assert sched["schedule"].minute == 30


# ─────────────────────────────────────────────────────────────────────────────
# Task registration — run_nightly_inference must be registered with Celery
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskRegistration:
    def test_nightly_task_registered(self):
        assert "tasks.run_nightly_inference" in app.tasks

    def test_nightly_task_is_bound(self):
        """bind=True gives access to self.retry on failure — verify the
        decorator is intact after any refactor."""
        assert run_nightly_inference.bind is True

    def test_nightly_task_max_retries(self):
        """Up to 3 retries — anything less and a single DB hiccup drops a day."""
        assert run_nightly_inference.max_retries == 3


# ─────────────────────────────────────────────────────────────────────────────
# Async-loop helper — _get_event_loop() must yield a runnable loop
# ─────────────────────────────────────────────────────────────────────────────
class TestEventLoopHelper:
    def test_returns_a_loop(self):
        from backend.tasks import _get_event_loop
        loop = _get_event_loop()
        assert not loop.is_closed()
        assert loop.is_running() is False

    def test_handles_closed_loop(self):
        """If the runtime closes the default loop, _get_event_loop must hand
        back a fresh one rather than raise."""
        from backend.tasks import _get_event_loop
        import asyncio

        previous = asyncio.get_event_loop()
        try:
            previous.close()
            loop = _get_event_loop()
            try:
                assert not loop.is_closed()
            finally:
                loop.close()
        finally:
            # Make sure subsequent tests get a sane loop back.
            asyncio.set_event_loop(asyncio.new_event_loop())
