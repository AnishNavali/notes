"""
dependencies.py – Reusable FastAPI dependencies for authentication and plan gating.

Usage in route handlers:
    from dependencies import CurrentUser, requires_plan

    @router.get("/protected")
    async def protected(user: CurrentUser):
        return {"hello": user["email"]}

    @router.get("/pro-only", dependencies=[Depends(requires_plan("pro"))])
    async def pro_feature(user: CurrentUser):
        ...

    @router.get("/paid", dependencies=[Depends(requires_plan("basic", "pro"))])
    async def paid_feature(user: CurrentUser):
        ...
"""

import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

import db as database

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Validate the Bearer JWT in the Authorization header and return the
    corresponding user document from MongoDB.

    Raises HTTP 401 for missing/invalid/expired tokens.
    Raises HTTP 404 if the token is valid but the user no longer exists.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise JWTError("Missing sub claim")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = database.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


# Convenience type alias for route signatures
CurrentUser = Annotated[dict, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Plan gating
# ---------------------------------------------------------------------------


def requires_plan(*plans: str):
    """
    Returns a FastAPI dependency that enforces subscription plan access.

    Raises HTTP 403 if:
      - The user's plan is not in the allowed `plans` tuple
      - The subscription status is 'expired'
      - The subscription is in 'grace_period' and the grace period has passed

    Usage:
        @router.get("/pro-only", dependencies=[Depends(requires_plan("pro"))])
        @router.get("/any-paid", dependencies=[Depends(requires_plan("basic", "pro"))])
    """

    async def _check(user: dict = Depends(get_current_user)):
        sub = user.get("subscription") or {}
        plan = sub.get("plan", "free")
        sub_status = sub.get("status", "active")
        grace_period_end = sub.get("grace_period_end")
        now = datetime.now(timezone.utc)

        # Hard expired — no access regardless of plan
        if sub_status == "expired":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your subscription has expired. Please renew to access this feature.",
            )

        # Grace period — check if it has lapsed
        if sub_status == "grace_period":
            if grace_period_end and now > _ensure_tz(grace_period_end):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your grace period has ended. Please update your payment method.",
                )
            # Still within grace period — allow access

        # Plan check
        if plan not in plans:
            required = " or ".join(f"'{p}'" for p in plans)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires a {required} plan. You are on the '{plan}' plan.",
            )

    return _check


def _ensure_tz(dt) -> datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    # Handle string datetimes stored by MongoDB serialisation
    if isinstance(dt, str):
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)
