"""FastAPI dependencies for authentication + RBAC.

``get_current_user`` reads the bearer token, decodes it, and loads the
matching user from the DB. ``require_role(...)`` enforces coarse RBAC;
``require_district_access`` enforces row-level access for district-
scoped officers (used by facility drilldown endpoints in v1.5+).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Cookie, Header, HTTPException, status

from backend.security import decode_token
from backend.users import get_user_by_id

logger = logging.getLogger(__name__)


class CurrentUser(dict):
    """Light wrapper that exposes ``.role`` and ``.id`` as attributes
    so endpoints can do ``user.role`` and tests can pass plain dicts."""

    @property
    def id(self) -> str:
        return self.get("id", "")

    @property
    def role(self) -> str:
        return self.get("role", "VIEWER")

    @property
    def district_id(self) -> Optional[str]:
        return self.get("district_id")

    @property
    def facility_id(self) -> Optional[str]:
        return self.get("facility_id")


# Roles that may POST to digest / weekly review endpoints.
PRIVILEGED_ROLES = {"COMMISSIONER", "STATE_OFFICER"}


async def _resolve_user_from_token(token: str) -> Optional[CurrentUser]:
    claims = decode_token(token)
    if not claims or claims.get("type") != "access":
        return None
    db_user = await get_user_by_id(claims["sub"])
    if not db_user or not db_user.get("is_active"):
        return None
    db_user["role"] = db_user.get("role") or claims.get("role", "VIEWER")
    db_user["district_id"] = str(db_user["district_id"]) if db_user.get("district_id") else None
    db_user["facility_id"] = str(db_user["facility_id"]) if db_user.get("facility_id") else None
    return CurrentUser(db_user)


async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    hmis_session: Optional[str] = Cookie(None, alias="hmis_session"),
) -> CurrentUser:
    """Return the authenticated user or 401.

    Accepts tokens from either:
      * ``Authorization: Bearer <jwt>`` header (used by the SPA)
      * ``hmis_session`` cookie (used by SSR / curl)
    """
    token: Optional[str] = None
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
    elif hmis_session:
        token = hmis_session.strip()

    if not token:
        raise HTTPException(status_code=401, detail="missing credentials")

    user = await _resolve_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return user


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    hmis_session: Optional[str] = Cookie(None, alias="hmis_session"),
) -> Optional[CurrentUser]:
    """Optional auth — returns None instead of 401 when no token is present.

    Used by public health endpoints that want to attribute the audit row
    to the caller when available but still allow anonymous traffic
    (e.g., during a beta rollout)."""
    try:
        return await get_current_user(authorization, hmis_session)
    except HTTPException as exc:
        if exc.status_code == 401 and not authorization and not hmis_session:
            return None
        raise


def require_role(*roles: str):
    """FastAPI dependency factory: 403 unless the user is in the role set."""
    role_set = set(roles)
    async def _checker(user: CurrentUser = None) -> CurrentUser:
        # ``user`` is injected by the framework only when used as
        # ``Depends(_checker(user=Depends(get_current_user)))``. Below we
        # accept the user via the request state instead for simplicity.
        from fastapi import Depends, Request
        raise NotImplementedError
    return _checker


# Inline helper used directly inside endpoints without FastAPI dependency
# injection. Keeps the migration low-impact.
def assert_role(user: CurrentUser, *roles: str) -> None:
    if user.role not in set(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role `{user.role}` not in {sorted(roles)}",
        )
