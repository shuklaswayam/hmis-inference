"""Security helpers — bcrypt password hashing + JWT signing.

Configuration:
  JWT_SECRET  — HMAC signing key (random per-environment, default for dev only)
  JWT_ALG     — default HS256
  JWT_TTL     — access token lifetime in seconds (default 4 hours)
  JWT_REFRESH_TTL — refresh token lifetime in seconds (default 7 days)

Token claims:
  sub : user id
  role: one of COMMISSIONER / STATE_OFFICER / DISTRICT_OFFICER / FACILITY_HEAD / VIEWER
  district_id / facility_id : optional scope (null for system-wide)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# bcrypt is optional — falling back to a hashlib PBKDF2 path keeps the test
# suite dependency-free. Production should still install bcrypt via
# ``pip install bcrypt``; the helper will use it automatically.
try:
    import bcrypt  # type: ignore
    _HAVE_BCRYPT = True
except ImportError:
    _HAVE_BCRYPT = False


_DEFAULT_DEV_SECRET = "artem-dev-secret-do-not-use-in-prod"


def jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", _DEFAULT_DEV_SECRET).strip() or _DEFAULT_DEV_SECRET


def access_ttl() -> int:
    return int(os.environ.get("JWT_TTL", str(4 * 3600)))


def refresh_ttl() -> int:
    return int(os.environ.get("JWT_REFRESH_TTL", str(7 * 24 * 3600)))


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    if _HAVE_BCRYPT:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    # PBKDF2 fallback (no external deps). Production should use bcrypt.
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return "pbkdf2$" + salt.hex() + "$" + dk.hex()


def verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("pbkdf2$"):
        try:
            _, salt_hex, dk_hex = hashed.split("$", 2)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(dk_hex)
            return hmac.compare_digest(
                hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000).hex(),
                expected.hex(),
            )
        except Exception:  # noqa: BLE001
            return False
    if _HAVE_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:  # noqa: BLE001
            return False
    return False


# ---------------------------------------------------------------------------
# JWT tokens (HMAC-SHA256, no extra deps)
# ---------------------------------------------------------------------------
def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    import base64
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def encode_token(
    *,
    sub: str,
    role: str,
    district_id: Optional[str] = None,
    facility_id: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    token_type: str = "access",
) -> str:
    """Return a signed JWT.

    ``ttl_seconds`` defaults to ``access_ttl()`` for type=access and
    ``refresh_ttl()`` for type=refresh.
    """
    if ttl_seconds is None:
        ttl_seconds = access_ttl() if token_type == "access" else refresh_ttl()

    header  = {"alg": "HS256", "typ": "JWT"}
    now      = int(time.time())
    payload = {
        "sub":        sub,
        "role":       role,
        "type":       token_type,
        "iat":        now,
        "exp":        now + ttl_seconds,
        "jti":        str(uuid.uuid4()),
        "district_id": district_id,
        "facility_id": facility_id,
    }
    body = _b64url(json.dumps(header,  separators=(",", ":")).encode("utf-8")) + "." + \
           _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(jwt_secret().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return body + "." + _b64url(sig)


def decode_token(token: str) -> Optional[dict]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return None
    body = (header_b64 + "." + payload_b64).encode("utf-8")
    expected_sig = hmac.new(jwt_secret().encode("utf-8"), body, hashlib.sha256).digest()
    actual_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:  # noqa: BLE001
        return None
    if payload.get("exp", 0) < int(time.time()):
        return None
    return payload
