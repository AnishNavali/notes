from pydantic import BaseModel
from typing import Optional


class User(BaseModel):
    """Stored in MongoDB users collection after first OAuth login."""

    id: str  # MongoDB _id as string
    provider: str  # "google" | "github" | "microsoft"
    provider_id: str  # sub / node_id / oid from the provider
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class TokenPayload(BaseModel):
    """Claims embedded inside the issued JWT."""

    sub: str  # MongoDB user _id
    email: str
    name: Optional[str] = None
    provider: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
