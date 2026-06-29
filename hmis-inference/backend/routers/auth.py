"""Auth router — login, refresh, me, logout-stub, register(privileged)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from backend.dependencies import CurrentUser, assert_role, get_current_user
from backend.security import (
    access_ttl, decode_token, encode_token, hash_password, verify_password,
)
from backend.users import create_user as db_create_user, get_user_by_email, get_user_by_id, update_last_login

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    district_id: Optional[str] = None
    facility_id: Optional[str] = None
    last_login_at: Optional[datetime] = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserOut


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: str = Field(pattern="^(COMMISSIONER|STATE_OFFICER|DISTRICT_OFFICER|FACILITY_HEAD|VIEWER)$")
    district_id: Optional[str] = None
    facility_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _user_to_out(user: dict) -> UserOut:
    return UserOut(
        id=str(user["id"]),
        email=user["email"],
        full_name=user.get("full_name") or user["email"],
        role=user["role"],
        district_id=str(user["district_id"]) if user.get("district_id") else None,
        facility_id=str(user["facility_id"]) if user.get("facility_id") else None,
        last_login_at=user.get("last_login_at"),
    )


async def _issue_pair(user: dict) -> dict:
    sub = str(user["id"])
    role = user["role"]
    district = str(user["district_id"]) if user.get("district_id") else None
    facility = str(user["facility_id"]) if user.get("facility_id") else None
    access = encode_token(sub=sub, role=role, district_id=district, facility_id=facility, token_type="access")
    refresh = encode_token(sub=sub, role=role, district_id=district, facility_id=facility, token_type="refresh")
    return {
        "access_token":  access,
        "refresh_token": refresh,
        "expires_in":    access_ttl(),
        "user": _user_to_out({**user, "last_login_at": datetime.now(timezone.utc)}).model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenPair)
async def login(req: LoginRequest) -> dict:
    user = await get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        )
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="account disabled")
    await update_last_login(str(user["id"]))
    return await _issue_pair(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(req: RefreshRequest) -> dict:
    claims = decode_token(req.refresh_token)
    if not claims or claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="invalid refresh token")
    db_user = await get_user_by_id(claims["sub"])
    if db_user is None or not db_user.get("is_active"):
        raise HTTPException(status_code=401, detail="user not found / inactive")
    return await _issue_pair(db_user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser = Depends(get_current_user)) -> UserOut:
    return _user_to_out(user)


@router.post("/register", response_model=UserOut)
async def register(
    req: RegisterRequest,
    actor: CurrentUser = Depends(get_current_user),
) -> UserOut:
    """Privileged route — COMMISSIONER / STATE_OFFICER only.

    Public signup is intentionally not exposed: the first COMMISSIONER
    is created via ``scripts/create_commissioner.py``, and from there
    this endpoint mints the rest of the directory.
    """
    assert_role(actor, "COMMISSIONER", "STATE_OFFICER")
    existing = await get_user_by_email(req.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    hashed = hash_password(req.password)
    new_user = await db_create_user(
        email=req.email,
        full_name=req.full_name,
        hashed_password=hashed,
        role=req.role,
        district_id=req.district_id,
        facility_id=req.facility_id,
    )
    return _user_to_out(new_user)


@router.post("/logout")
async def logout() -> dict:
    """Stateless logout — the client drops the tokens. The endpoint
    exists so the SPA can record an audit log entry on its way out."""
    return {"ok": True}
