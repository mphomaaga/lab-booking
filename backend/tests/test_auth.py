"""`POST /auth/login` and `GET /me` (US-1, rules 5.13, 5.14)."""

import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.services import auth as auth_service

INVALID_CREDENTIALS = {
    "error": {
        "code": "invalid_credentials",
        "message": "Student number or password is incorrect.",
    }
}


def _login(client, student_number, password):
    return client.post("/auth/login", json={"student_number": student_number, "password": password})


# --- login: success -------------------------------------------------------------------


def test_login_success_returns_token_and_user(client, user_factory, frozen_now):
    user = user_factory(student_number="20260001", password="s3cret")

    response = _login(client, "20260001", "s3cret")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_at", "user"}
    assert body["token_type"] == "bearer"
    assert body["user"] == {"id": user.id, "student_number": "20260001", "is_admin": False}
    claims = jwt.decode(
        body["access_token"],
        get_settings().JWT_SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["sub"] == str(user.id)


def test_login_expires_at_is_login_time_plus_expiry_in_utc_z(client, user_factory, frozen_now):
    user_factory(student_number="20260001")

    body = _login(client, "20260001", "password").json()

    minutes = get_settings().JWT_EXPIRE_MINUTES
    assert minutes == 480
    expected = frozen_now.now + timedelta(minutes=minutes)
    assert body["expires_at"] == "2026-01-05T16:00:00Z"
    assert body["expires_at"] == expected.strftime("%Y-%m-%dT%H:%M:%SZ")
    claims = jwt.decode(
        body["access_token"],
        get_settings().JWT_SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["exp"] == int(expected.replace(tzinfo=UTC).timestamp())


def test_login_respects_configured_expiry(client, user_factory, frozen_now, monkeypatch):
    user_factory(student_number="20260001")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")
    get_settings.cache_clear()
    try:
        body = _login(client, "20260001", "password").json()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    assert body["expires_at"] == "2026-01-05T09:00:00Z"


def test_admin_logs_in_through_the_same_endpoint(client, admin_factory):
    admin = admin_factory(student_number="admin01", password="adminpass")

    response = _login(client, "admin01", "adminpass")

    assert response.status_code == 200
    assert response.json()["user"] == {"id": admin.id, "student_number": "admin01", "is_admin": True}


# --- login: student number matching -----------------------------------------------------


@pytest.mark.parametrize("attempt", ["ABC123", "abc123 ", " abc123", "AbC123"])
def test_student_number_is_matched_exactly_as_stored(client, user_factory, attempt):
    user_factory(student_number="abc123")

    response = _login(client, attempt, "password")

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_student_number_with_any_format_can_log_in(client, user_factory):
    # No format check (US-1): whatever is stored is what must be typed.
    user_factory(student_number=" Odd-Number_1 ")

    assert _login(client, " Odd-Number_1 ", "password").status_code == 200


# --- login: failures ----------------------------------------------------------------------


def test_unknown_student_number_and_wrong_password_are_identical(client, user_factory):
    user_factory(student_number="20260001")

    unknown = _login(client, "29999999", "password")
    wrong = _login(client, "20260001", "wrong-password")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == INVALID_CREDENTIALS
    assert unknown.headers.get("www-authenticate") == wrong.headers.get("www-authenticate")


def test_both_failures_run_one_password_check(client, user_factory, monkeypatch):
    """An unknown student number does the same bcrypt work as a wrong password."""
    user_factory(student_number="20260001")
    calls = []
    real = auth_service.verify_password

    def counting(plain, hashed):
        calls.append(hashed)
        return real(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", counting)

    _login(client, "29999999", "password")
    _login(client, "20260001", "wrong-password")

    assert len(calls) == 2
    assert all(h.startswith("$2") for h in calls)


def test_failed_login_does_not_log_or_echo_the_password(client, user_factory, caplog):
    user_factory(student_number="20260001")
    secret = "hunter2-very-secret"

    with caplog.at_level(logging.DEBUG):
        unknown = _login(client, "29999999", secret)
        wrong = _login(client, "20260001", secret)

    for response in (unknown, wrong):
        assert secret not in response.text
        assert "$2" not in response.text
    assert secret not in caplog.text
    assert "$2b$" not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"password": "password"},
        {"student_number": "20260001"},
        {"student_number": "", "password": "password"},
        {"student_number": "20260001", "password": ""},
        {"student_number": "x" * 33, "password": "password"},
        {"student_number": "20260001", "password": "x" * 129},
        {"student_number": "20260001", "password": "password", "remember_me": True},
        {"student_number": None, "password": "password"},
        {"student_number": 20260001, "password": "password"},
    ],
)
def test_invalid_login_body_is_a_validation_error(client, user_factory, payload):
    user_factory(student_number="20260001")

    response = client.post("/auth/login", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_student_number_at_its_maximum_length_can_log_in(client, user_factory):
    user_factory(student_number="2" * 32, password="p" * 72)  # bcrypt's own limit is 72 bytes

    assert _login(client, "2" * 32, "p" * 72).status_code == 200


def test_password_at_the_schema_maximum_is_a_401_not_a_server_error(client, user_factory):
    # LoginRequest allows 128 characters but bcrypt only takes 72 bytes, so no stored
    # password can be that long: it must be rejected as a wrong password, not crash.
    user_factory(student_number="20260001")

    response = _login(client, "20260001", "p" * 128)

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_non_json_body_is_a_validation_error(client):
    response = client.post("/auth/login", content="not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- GET /me ------------------------------------------------------------------------------------


def test_me_with_the_login_token_returns_the_user(client, user_factory):
    user = user_factory(student_number="20260001")
    token = _login(client, "20260001", "password").json()["access_token"]

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"id": user.id, "student_number": "20260001", "is_admin": False}


def test_me_for_an_admin_reports_is_admin(client, admin_factory):
    admin = admin_factory(student_number="admin01")
    token = _login(client, "admin01", "password").json()["access_token"]

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json() == {"id": admin.id, "student_number": "admin01", "is_admin": True}


NOT_AUTHENTICATED = {"error": {"code": "not_authenticated", "message": "Please log in."}}


def test_me_without_a_token_is_401(client):
    response = client.get("/me")

    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


@pytest.mark.parametrize(
    "header",
    ["Bearer not-a-token", "Bearer a.b.c", "Bearer ", "Basic dXNlcjpwYXNz", "garbage"],
)
def test_me_with_a_malformed_token_is_401(client, header):
    response = client.get("/me", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_with_an_expired_token_is_401(client, user_factory, frozen_now):
    user_factory(student_number="20260001")
    login = _login(client, "20260001", "password").json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.get("/me", headers=headers).status_code == 200

    frozen_now.set(datetime(2026, 1, 5, 16, 0))  # exactly expires_at

    response = client.get("/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_me_just_before_expiry_still_works(client, user_factory, frozen_now):
    user_factory(student_number="20260001")
    token = _login(client, "20260001", "password").json()["access_token"]

    frozen_now.set(datetime(2026, 1, 5, 15, 59, 59))

    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_me_with_a_token_signed_with_another_secret_is_401(client, user_factory):
    user = user_factory()
    now = int(datetime.now(UTC).timestamp())
    forged = jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + 3600}, "some-other-secret-0123456789abcdef", "HS256"
    )

    response = client.get("/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


# --- no extra endpoints ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/auth/register"),
        ("post", "/auth/signup"),
        ("post", "/auth/logout"),
        ("post", "/auth/refresh"),
        ("post", "/auth/password"),
        ("post", "/auth/change-password"),
        ("post", "/auth/reset-password"),
        ("put", "/me/password"),
        ("post", "/me/password"),
        ("post", "/users"),
    ],
)
def test_no_registration_logout_refresh_or_password_endpoints(client, method, path):
    response = getattr(client, method)(path, json={})

    assert response.status_code in (404, 405)


def test_auth_router_exposes_only_login_and_me():
    from app.api.auth import router

    routes = {(m, r.path) for r in router.routes for m in r.methods}
    assert routes == {("POST", "/auth/login"), ("GET", "/me")}
