"""
auth.py – OAuth 2.0 Authorization Code flow for Google, GitHub, and Microsoft.

Flow per provider:
  1. GET /auth/{provider}/login   → redirect to provider consent screen
  2. GET /auth/{provider}/callback → exchange code for tokens, fetch user info,
                                     upsert user in MongoDB, issue JWT, redirect to frontend

Environment variables required (see .env):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
  MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID
  JWT_SECRET_KEY          – random secret for signing JWTs
  FRONTEND_URL            – where to redirect after login (e.g. http://localhost:3000)
  APP_BASE_URL            – this server's public URL (e.g. http://localhost:8000)
"""

import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import jwt

import db as database
from models import TokenResponse

router = APIRouter(tags=["auth"])

# ---------------------------------------------------------------------------
# Config (loaded from environment)
# ---------------------------------------------------------------------------

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

PROVIDERS = {
    "google": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": "openid email profile",
    },
    "github": {
        "client_id": os.getenv("GITHUB_CLIENT_ID", ""),
        "client_secret": os.getenv("GITHUB_CLIENT_SECRET", ""),
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scopes": "read:user user:email",
    },
    "microsoft": {
        "client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
        "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        "tenant_id": os.getenv("MICROSOFT_TENANT_ID", "common"),
        "auth_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "scopes": "openid email profile User.Read",
    },
}


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _redirect_uri(provider: str) -> str:
    return f"{APP_BASE_URL}/auth/{provider}/callback"


def _get_provider(provider: str) -> dict:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    cfg = PROVIDERS[provider]
    if not cfg.get("client_id"):
        raise HTTPException(
            status_code=503,
            detail=f"{provider.title()} OAuth is not configured. "
            f"Set {provider.upper()}_CLIENT_ID and {provider.upper()}_CLIENT_SECRET in .env",
        )
    return cfg


# ---------------------------------------------------------------------------
# Step 1 – Redirect to provider
# ---------------------------------------------------------------------------


@router.get("/auth/{provider}/login")
async def oauth_login(provider: str):
    """Redirect the browser to the provider's consent screen."""
    cfg = _get_provider(provider)

    auth_url = cfg["auth_url"]
    if provider == "microsoft":
        auth_url = auth_url.format(tenant=cfg["tenant_id"])

    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": _redirect_uri(provider),
        "response_type": "code",
        "scope": cfg["scopes"],
    }
    if provider == "google":
        params["access_type"] = "offline"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{auth_url}?{query}")


# ---------------------------------------------------------------------------
# Step 2 – Callback: exchange code → tokens → user info → JWT
# ---------------------------------------------------------------------------


@router.get("/auth/{provider}/callback", response_model=TokenResponse)
async def oauth_callback(provider: str, request: Request):
    """Handle the OAuth callback, upsert the user, and return a JWT."""
    cfg = _get_provider(provider)
    code = request.query_params.get("code")
    if not code:
        error = request.query_params.get("error", "no_code")
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    async with httpx.AsyncClient() as client:
        # ---- exchange code for access token --------------------------------
        token_url = cfg["token_url"]
        if provider == "microsoft":
            token_url = token_url.format(tenant=cfg["tenant_id"])

        token_data = {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "redirect_uri": _redirect_uri(provider),
            "grant_type": "authorization_code",
        }

        headers = {"Accept": "application/json"}
        token_resp = await client.post(token_url, data=token_data, headers=headers)

        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Token exchange failed: {token_resp.text}",
            )

        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=502, detail="No access_token in provider response"
            )

        # ---- fetch user info -----------------------------------------------
        userinfo_url = cfg["userinfo_url"]
        info_resp = await client.get(
            userinfo_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

        if info_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"User info fetch failed: {info_resp.text}",
            )

        info = info_resp.json()

    # ---- normalise provider-specific shapes --------------------------------
    if provider == "google":
        provider_id = info["sub"]
        email = info.get("email", "")
        name = info.get("name")
        picture = info.get("picture")

    elif provider == "github":
        provider_id = str(info["id"])
        email = info.get("email") or ""
        # GitHub sometimes hides the email — fetch from /user/emails if missing
        if not email:
            async with httpx.AsyncClient() as client:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                if emails_resp.status_code == 200:
                    for e in emails_resp.json():
                        if e.get("primary") and e.get("verified"):
                            email = e["email"]
                            break
        name = info.get("name") or info.get("login")
        picture = info.get("avatar_url")

    elif provider == "microsoft":
        provider_id = info.get("id", "")
        email = info.get("mail") or info.get("userPrincipalName", "")
        name = info.get("displayName")
        picture = None

    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Could not retrieve a verified email from the OAuth provider.",
        )

    # ---- upsert user in MongoDB --------------------------------------------
    user = database.upsert_oauth_user(
        provider=provider,
        provider_id=provider_id,
        email=email,
        name=name,
        picture=picture,
    )
    


    # ---- issue JWT ---------------------------------------------------------
    jwt_token = create_access_token(
        {
            "sub": user["_id"],
            "email": email,
            "name": name,
            "provider": provider,
        }
    )

    # Redirect to frontend with token in query param, or return JSON
    # Change this to a redirect if your frontend prefers it:
    return RedirectResponse(url=f"{FRONTEND_URL}/?token={jwt_token}")
    # return TokenResponse(access_token=jwt_token)

# ---------------------------------------------------------------------------
# Introspect / me
# ---------------------------------------------------------------------------


@router.get("/auth/me")
async def get_me(request: Request):
    """Return current user info decoded from the Authorization header JWT."""
    from dependencies import get_current_user  # local import avoids circular dep

    user = await get_current_user(request)
    return user
