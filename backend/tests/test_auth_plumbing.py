"""Auth plumbing: JWT helpers, `get_current_user` and `require_admin`."""

from datetime import UTC, timedelta

import jwt
import pytest
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_admin
from app.core.config import get_settings
from app.core.security import InvalidTokenError, create_access_token, decode_access_token
from app.main import app
from app.models import User

# Test-only routes: app code has no guarded route yet.
_router = APIRouter()


@_router.get("/_test/me")
def _me(user: User = Depends(get_current_user)) -> dict[str, int]:
    return {"id": user.id}


@_router.get("/_test/admin")
def _admin(user: User = Depends(require_admin)) -> dict[str, int]:
    return {"id": user.id}


app.include_router(_router)

NOT_AUTHENTICATED = {"error": {"code": "not_authenticated", "message": "Please log in."}}


def _token_for(sub, /, secret=None, **claims) -> str:
    """A hand-built token; `claims` override the defaults (`iat`, `exp` in epoch seconds)."""
    from app.core import clock

    now = int(clock.now_utc().replace(tzinfo=UTC).timestamp())
    payload = {"sub": str(sub), "iat": now, "exp": now + 3600, **claims}
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, secret or get_settings().JWT_SECRET, algorithm="HS256")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_jwt_secret_is_set_for_tests() -> None:
    assert get_settings().JWT_SECRET == "test-secret-for-lab-booking-tests-0123456789"


# -- get_current_user: success and every 401 ----------------------------------


def test_valid_token_returns_the_user(client, user_factory, auth_headers) -> None:
    user = user_factory()
    response = client.get("/_test/me", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json() == {"id": user.id}


def test_missing_header_is_401(client) -> None:
    response = client.get("/_test/me")
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


@pytest.mark.parametrize(
    "header",
    ["Bearer", "Bearer not-a-jwt", "Basic abc", "Token abc", "abc.def.ghi"],
)
def test_malformed_token_is_401(client, header) -> None:
    response = client.get("/_test/me", headers={"Authorization": header})
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_wrongly_signed_token_is_401(client, user_factory) -> None:
    user = user_factory()
    token = _token_for(user.id, secret="some-other-secret")
    response = client.get("/_test/me", headers=_bearer(token))
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_expired_token_is_401(client, user_factory, auth_headers, frozen_now) -> None:
    user = user_factory()
    headers = auth_headers(user)
    assert client.get("/_test/me", headers=headers).status_code == 200
    frozen_now.advance(minutes=480)  # exp is reached
    response = client.get("/_test/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_token_for_deleted_user_is_401(client, session, user_factory, auth_headers) -> None:
    user = user_factory()
    headers = auth_headers(user)
    session.delete(user)
    session.commit()
    response = client.get("/_test/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


@pytest.mark.parametrize("sub", ["abc", "", "1.5"])
def test_non_numeric_subject_is_401(client, sub) -> None:
    response = client.get("/_test/me", headers=_bearer(_token_for(sub)))
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


@pytest.mark.parametrize("missing", ["sub", "iat", "exp"])
def test_token_missing_a_claim_is_401(client, user_factory, missing) -> None:
    user = user_factory()
    response = client.get("/_test/me", headers=_bearer(_token_for(user.id, **{missing: None})))
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_unsigned_token_is_401(client, user_factory) -> None:
    user = user_factory()
    token = jwt.encode({"sub": str(user.id), "iat": 0, "exp": 9999999999}, key=None, algorithm="none")
    response = client.get("/_test/me", headers=_bearer(token))
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


# -- require_admin ---------------------------------------------------------------


def test_non_admin_gets_403(client, user_factory, auth_headers) -> None:
    response = client.get("/_test/admin", headers=auth_headers(user_factory()))
    assert response.status_code == 403
    assert response.json() == {"error": {"code": "admin_required", "message": "Admins only."}}


def test_admin_gets_200(client, admin_factory, auth_headers) -> None:
    admin = admin_factory()
    response = client.get("/_test/admin", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json() == {"id": admin.id}


def test_admin_route_without_token_is_401(client) -> None:
    response = client.get("/_test/admin")
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_is_admin_comes_from_the_database_not_the_token(
    client, session, user_factory, auth_headers
) -> None:
    user = user_factory()
    claims_token = _token_for(user.id, is_admin=True)  # a forged claim is ignored
    assert client.get("/_test/admin", headers=_bearer(claims_token)).status_code == 403

    headers = auth_headers(user)
    assert client.get("/_test/admin", headers=headers).status_code == 403
    user.is_admin = True  # promoted after the token was issued
    session.commit()
    assert client.get("/_test/admin", headers=headers).status_code == 200
    user.is_admin = False  # and demoted again
    session.commit()
    assert client.get("/_test/admin", headers=headers).status_code == 403


# -- token creation and lifetime (rule 5.14) -----------------------------------------


def test_token_claims_and_default_lifetime(frozen_now, monkeypatch) -> None:
    monkeypatch.delenv("JWT_EXPIRE_MINUTES", raising=False)
    get_settings.cache_clear()
    try:
        token, expires_at = create_access_token(7)
    finally:
        get_settings.cache_clear()
    claims = jwt.decode(
        token,
        get_settings().JWT_SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert set(claims) == {"sub", "iat", "exp"}
    assert claims["sub"] == "7"
    assert expires_at == frozen_now.now + timedelta(minutes=480)
    assert claims["exp"] - claims["iat"] == 480 * 60
    assert jwt.get_unverified_header(token)["alg"] == "HS256"


def test_lifetime_follows_jwt_expire_minutes(frozen_now, monkeypatch) -> None:
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "30")
    get_settings.cache_clear()
    try:
        token, expires_at = create_access_token(1)
        claims = decode_access_token(token)
    finally:
        get_settings.cache_clear()
    assert expires_at == frozen_now.now + timedelta(minutes=30)
    assert claims["exp"] - claims["iat"] == 30 * 60


def test_decode_returns_claims_until_expiry(frozen_now) -> None:
    token, _ = create_access_token(5)
    assert decode_access_token(token)["sub"] == "5"
    frozen_now.advance(minutes=479, seconds=59)
    assert decode_access_token(token)["sub"] == "5"
    frozen_now.advance(seconds=1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_rejects_garbage() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("garbage")
