import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi import APIRouter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel, ConfigDict  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.errors import ApiError  # noqa: E402
from app.main import app  # noqa: E402


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_number: str


_router = APIRouter()


@_router.post("/_test/validate")
def _validate(payload: Payload) -> dict[str, str]:
    return {"ok": payload.student_number}


@_router.get("/_test/api-error")
def _api_error() -> None:
    raise ApiError(409, "slot_full", "This slot is full.")


@_router.get("/_test/boom")
def _boom() -> None:
    raise RuntimeError("secret internal detail")


app.include_router(_router)

client = TestClient(app, raise_server_exceptions=False)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_error() -> None:
    response = client.get("/_test/api-error")
    assert response.status_code == 409
    assert response.json() == {"error": {"code": "slot_full", "message": "This slot is full."}}


def test_unknown_route_is_not_found() -> None:
    response = client.get("/no-such-route")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)
    assert "details" not in body["error"]


def test_validation_error_has_details() -> None:
    response = client.post("/_test/validate", json={})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"] == [{"loc": ["body", "student_number"], "msg": "Field required"}]


def test_unknown_field_is_rejected() -> None:
    response = client.post("/_test/validate", json={"student_number": "1", "extra": 1})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unhandled_exception_is_internal_error() -> None:
    response = client.get("/_test/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


def test_now_utc_is_naive_utc() -> None:
    now = clock.now_utc()
    assert now.tzinfo is None
    assert abs((datetime.now(UTC).replace(tzinfo=None) - now).total_seconds()) < 5


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "s")
    for name in ("JWT_EXPIRE_MINUTES", "DATABASE_URL", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()  # type: ignore[call-arg]
    assert settings.JWT_EXPIRE_MINUTES == 480
    assert settings.DATABASE_URL == "sqlite:///./lab_booking.db"
    assert settings.cors_origins_list == ["http://localhost:5173"]


def test_cors_origins_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "s")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings().cors_origins_list == ["http://a.test", "http://b.test"]  # type: ignore[call-arg]


def test_missing_jwt_secret_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            get_settings()
    finally:
        get_settings.cache_clear()
