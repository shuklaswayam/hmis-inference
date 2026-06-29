"""
Unit tests for the inference audit query store.

Pure-Python target — DB-touching helpers route through
test_inference_router_audit with mocks; we focus on the window parser
and JSON-decoding helpers here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from backend.inference.store import parse_window_to_hours, _decode_jsonb


def test_window_parsing_handles_short_windows():
    assert parse_window_to_hours("1h") == 1
    assert parse_window_to_hours("24h") == 24


def test_window_parsing_handles_day_windows():
    assert parse_window_to_hours("7d") == 168
    assert parse_window_to_hours("30d") == 720


def test_window_parsing_defaults_to_24h_when_unknown():
    assert parse_window_to_hours("lol") == 24
    assert parse_window_to_hours("") == 24


def test_decode_jsonb_returns_dict_for_dict_input():
    assert _decode_jsonb({"a": 1}) == {"a": 1}


def test_decode_jsonb_parses_strings():
    assert _decode_jsonb('{"a": 2}') == {"a": 2}


def test_decode_jsonb_handles_invalid_strings_gracefully():
    assert _decode_jsonb("not-json") == {"_raw": "not-json"}


def test_decode_jsonb_handles_none():
    assert _decode_jsonb(None) == {}
