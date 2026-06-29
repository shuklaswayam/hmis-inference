"""DB access for users + role lookups."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.database import Database

logger = logging.getLogger(__name__)


async def get_user_by_email(email: str) -> Optional[dict]:
    row = await Database.fetchrow(
        """
        SELECT id, email, full_name, hashed_password, role,
               district_id, facility_id, is_active
        FROM users
        WHERE email = $1
        """,
        email.strip().lower(),
    )
    if row is None:
        return None
    return dict(row)


async def get_user_by_id(user_id: str) -> Optional[dict]:
    row = await Database.fetchrow(
        """
        SELECT id, email, full_name, role,
               district_id, facility_id, is_active
        FROM users
        WHERE id = $1::uuid
        """,
        user_id,
    )
    return dict(row) if row else None


async def create_user(
    *,
    email: str,
    full_name: str,
    hashed_password: str,
    role: str,
    district_id: Optional[str] = None,
    facility_id: Optional[str] = None,
) -> dict:
    row = await Database.fetchrow(
        """
        INSERT INTO users (email, full_name, hashed_password, role,
                           district_id, facility_id)
        VALUES ($1, $2, $3, $4, NULLIF($5, '')::uuid, NULLIF($6, '')::uuid)
        RETURNING id, email, full_name, role, district_id, facility_id
        """,
        email.strip().lower(),
        full_name,
        hashed_password,
        role,
        district_id or "",
        facility_id or "",
    )
    return dict(row)


async def update_last_login(user_id: str) -> None:
    try:
        await Database.execute(
            "UPDATE users SET last_login_at = $1 WHERE id = $2::uuid",
            datetime.now(timezone.utc),
            user_id,
        )
    except Exception:  # noqa: BLE001
        logger.debug("update_last_login failed", exc_info=True)
