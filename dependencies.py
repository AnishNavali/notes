"""
dependencies.py – Reusable FastAPI dependencies for authentication.

Usage in route handlers:
    from dependencies import CurrentUser

    @router.get("/protected")
    async def protected(user: CurrentUser):
        return {"hello": user["email"]}
"""

import os
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
