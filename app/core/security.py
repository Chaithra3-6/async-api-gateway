"""JWT creation and verification.

A JWT is a signed token that proves who the caller is. We sign with a shared
secret (HS256). The token carries a subject (`sub`, e.g. the username) and an
expiry (`exp`); verification fails if the signature is wrong or the token has
expired.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt  # PyJWT


class TokenError(Exception):
    """Raised when a token is missing, malformed, tampered with, or expired."""


def create_access_token(
    subject: str,
    *,
    secret: str,
    expires_minutes: int = 30,
    algorithm: str = "HS256",
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(
    token: str,
    *,
    secret: str,
    algorithm: str = "HS256",
) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc
