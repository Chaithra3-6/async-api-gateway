from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    TokenError,
)

SECRET = "unit-test-secret"


def test_token_round_trips_subject():
    token = create_access_token("alice", secret=SECRET)
    payload = decode_access_token(token, secret=SECRET)
    assert payload["sub"] == "alice"


def test_wrong_secret_is_rejected():
    token = create_access_token("alice", secret=SECRET)
    with pytest.raises(TokenError):
        decode_access_token(token, secret="different-secret")


def test_expired_token_is_rejected():
    token = create_access_token(
        "alice",
        secret=SECRET,
        expires_minutes=-1,
        now=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    with pytest.raises(TokenError):
        decode_access_token(token, secret=SECRET)


def test_garbage_token_is_rejected():
    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt", secret=SECRET)
