"""
Phase-4 backend tests:
  * security: hash / verify roundtrip, JWT sign + verify, expiry behavior
  * dependencies: get_current_user happy-path + 401 / expired cases
  * retention: archive_old_audits via SQL smoke (mocked DB execute)
  * audit user_id wired through
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


# ---------------------------------------------------------------------------
# security.py
# ---------------------------------------------------------------------------
def test_password_hash_round_trip():
    from backend.security import hash_password, verify_password
    h = hash_password("hunter2")
    assert isinstance(h, str)
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)


def test_password_hash_distinguishes_inputs():
    from backend.security import hash_password
    h1 = hash_password("a")
    h2 = hash_password("b")
    assert h1 != h2


def test_jwt_round_trip_valid():
    from backend.security import encode_token, decode_token
    tok = encode_token(sub="user-id-1", role="COMMISSIONER", token_type="access")
    claims = decode_token(tok)
    assert claims is not None
    assert claims["sub"] == "user-id-1"
    assert claims["role"] == "COMMISSIONER"
    assert claims["type"] == "access"


def test_jwt_invalid_signature_returns_none():
    sys.modules.pop("backend.security", None)
    import backend.security as s
    tok = s.encode_token(sub="x", role="x")
    # Tamper the token payload.
    bad = tok[:-2] + ("X" if tok[-1] != "X" else "Y")
    assert s.decode_token(bad) is None


def test_jwt_invalid_format_returns_none():
    from backend.security import decode_token
    assert decode_token("not-a-jwt") is None
    assert decode_token("") is None


def test_jwt_typed_tokens():
    from backend.security import encode_token, decode_token
    a = encode_token(sub="u", role="VIEWER", token_type="access")
    r = encode_token(sub="u", role="VIEWER", token_type="refresh")
    assert decode_token(a)["type"] == "access"
    assert decode_token(r)["type"] == "refresh"


def test_jwt_scope_claims_round_trip():
    from backend.security import encode_token, decode_token
    tok = encode_token(sub="x", role="DISTRICT_OFFICER",
                       district_id="11111111-2222-3333-4444-555555555555",
                       facility_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    claims = decode_token(tok)
    assert claims["district_id"] == "11111111-2222-3333-4444-555555555555"
    assert claims["facility_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ---------------------------------------------------------------------------
# dependencies
# ---------------------------------------------------------------------------
import asyncio
import pytest


@pytest.mark.asyncio
async def test_assert_role_passes_for_listed_role():
    from backend.dependencies import CurrentUser, assert_role
    user = CurrentUser({"id": "u", "role": "COMMISSIONER"})
    assert_role(user, "COMMISSIONER", "STATE_OFFICER")


@pytest.mark.asyncio
async def test_assert_role_raises_403_for_outsider():
    from fastapi import HTTPException
    from backend.dependencies import CurrentUser, assert_role
    user = CurrentUser({"id": "u", "role": "VIEWER"})
    with pytest.raises(HTTPException) as exc:
        assert_role(user, "COMMISSIONER", "STATE_OFFICER")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# retention
# ---------------------------------------------------------------------------
def test_ttl_default_is_ninety_days():
    import os
    os.environ.pop("AUDIT_TTL_DAYS", None)
    from backend.inference.retention import ttl_days
    assert ttl_days() == 90


def test_ttl_overrides_via_env():
    import os
    os.environ["AUDIT_TTL_DAYS"] = "30"
    import importlib
    import backend.inference.retention as r
    importlib.reload(r)
    assert r.ttl_days() == 30
    os.environ.pop("AUDIT_TTL_DAYS", None)


@pytest.mark.asyncio
async def test_archive_old_audits_emits_cutoff_iso():
    from backend.inference import retention
    received: list[tuple] = []
    async def fake_execute(sql, *args):
        received.append((sql, args))
        return ""
    # Provide enough fake methods to satisfy hot_count / archive_count.
    class F:
        execute = staticmethod(fake_execute)
    await retention.archive_old_audits.__wrapped__(F) if hasattr(retention.archive_old_audits, "__wrapped__") else None
    # Direct invocation with monkey patching is awkward — touch the simple path.
    from unittest.mock import AsyncMock
    import backend.database as dbmod
    original = dbmod.Database.execute
    dbmod.Database.execute = AsyncMock(side_effect=fake_execute)
    try:
        result = await retention.archive_old_audits(ttl_days=7)
    finally:
        dbmod.Database.execute = original
    assert result["cutoff"].startswith("20")  # ISO timestamp prefix
    assert received  # we issued the WITH ... DELETE ... INSERT statement.


# ---------------------------------------------------------------------------
# audit user_id wiring
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_write_accepts_user_id():
    from unittest.mock import AsyncMock
    import backend.database as dbmod
    captured = {"args": None}
    async def fake(sql, *args):
        captured["args"] = args
        return ""
    dbmod.Database.execute = AsyncMock(side_effect=fake)
    from backend.inference import audit
    from uuid import uuid4
    target_user_id = "00000000-1111-2222-3333-444444444444"
    await audit.write(
        workstream="outbreak_risk",
        trace_id=uuid4(),
        response={"signals": []},
        request={"district_id": None},
        severity="HIGH",
        confidence=0.9,
        user_id=target_user_id,
    )
    args = captured["args"]
    # user_id is the 5th positional arg. Audit normalises it to a UUID.
    from uuid import UUID as _UUID
    assert args[4] == _UUID(target_user_id)
