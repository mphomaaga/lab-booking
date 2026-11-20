"""The Pydantic schemas must match docs/api.yaml."""

from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

from app import schemas

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "docs" / "api.yaml"
CONTRACT: dict[str, Any] = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
CONTRACT_SCHEMAS: dict[str, Any] = CONTRACT["components"]["schemas"]


def _ref_name(node: dict[str, Any]) -> str:
    return node["$ref"].rsplit("/", 1)[-1]


def _adapter_for(schema: dict[str, Any]) -> TypeAdapter[Any]:
    """Build a validator for a contract schema that is a $ref or an array of $refs."""
    if "$ref" in schema:
        return TypeAdapter(getattr(schemas, _ref_name(schema)))
    if schema.get("type") == "array" and "$ref" in schema["items"]:
        return TypeAdapter(list[getattr(schemas, _ref_name(schema["items"]))])
    raise AssertionError(f"unsupported schema in contract: {schema}")


def _examples() -> list[Any]:
    """Every (schema, example) pair in the contract's paths and reusable responses."""
    found: list[Any] = []

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            if "schema" in node and "example" in node and isinstance(node["schema"], dict):
                if "$ref" in node["schema"] or "items" in node["schema"]:
                    found.append(pytest.param(node["schema"], node["example"], id=where))
            for key, value in node.items():
                walk(value, f"{where}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{where}/{index}")

    walk(CONTRACT["paths"], "paths")
    walk(CONTRACT["components"]["responses"], "responses")
    return found


EXAMPLES = _examples()


def test_contract_has_examples() -> None:
    assert len(EXAMPLES) >= 10


@pytest.mark.parametrize(("schema", "example"), EXAMPLES)
def test_contract_example_validates(schema: dict[str, Any], example: Any) -> None:
    adapter = _adapter_for(schema)
    parsed = adapter.validate_python(example)
    # Round-trips back to the same payload (the examples contain no optional extras).
    assert adapter.dump_python(parsed, mode="json", exclude_none=True) == example


# ---- one model or enum per contract schema ----

OBJECT_SCHEMAS = [
    name
    for name, spec in CONTRACT_SCHEMAS.items()
    if spec.get("type") == "object" and name != "Error"
]
ENUM_SCHEMAS = [name for name, spec in CONTRACT_SCHEMAS.items() if "enum" in spec]


@pytest.mark.parametrize("name", OBJECT_SCHEMAS)
def test_model_fields_match_contract(name: str) -> None:
    spec = CONTRACT_SCHEMAS[name]
    model = getattr(schemas, name)
    assert issubclass(model, BaseModel)
    assert set(model.model_fields) == set(spec["properties"])
    required = {field for field, info in model.model_fields.items() if info.is_required()}
    assert required == set(spec["required"])


@pytest.mark.parametrize("name", ENUM_SCHEMAS)
def test_enum_values_match_contract(name: str) -> None:
    enum = getattr(schemas, name)
    assert issubclass(enum, StrEnum)
    assert [member.value for member in enum] == CONTRACT_SCHEMAS[name]["enum"]


def test_every_contract_schema_has_a_model() -> None:
    for name in CONTRACT_SCHEMAS:
        assert hasattr(schemas, name), name


def test_error_envelope_matches_contract() -> None:
    body = CONTRACT_SCHEMAS["Error"]["properties"]["error"]
    assert set(schemas.ErrorBody.model_fields) == set(body["properties"])
    required = {f for f, i in schemas.ErrorBody.model_fields.items() if i.is_required()}
    assert required == set(body["required"])


def test_enums_have_contract_values() -> None:
    assert [m.value for m in schemas.DayStatus] == ["open", "closed", "weekend"]
    assert [m.value for m in schemas.BookingStatus] == ["active", "cancelled"]


# ---- datetimes (rule 5.15) ----


def _slot_ref(start: datetime, end: datetime) -> schemas.SlotRef:
    return schemas.SlotRef(id=1, start_time=start, end_time=end)


def test_naive_datetime_serialises_as_utc_with_z() -> None:
    slot = _slot_ref(datetime(2026, 11, 19, 6, 0, 0), datetime(2026, 11, 19, 7, 0, 0))
    assert slot.model_dump(mode="json") == {
        "id": 1,
        "start_time": "2026-11-19T06:00:00Z",
        "end_time": "2026-11-19T07:00:00Z",
    }


def test_aware_datetime_is_converted_to_utc() -> None:
    sast = timezone(timedelta(hours=2))
    slot = _slot_ref(
        datetime(2026, 11, 19, 8, 0, 0, tzinfo=sast),
        datetime(2026, 11, 19, 9, 0, 0, tzinfo=UTC),
    )
    assert slot.model_dump(mode="json")["start_time"] == "2026-11-19T06:00:00Z"
    assert slot.model_dump(mode="json")["end_time"] == "2026-11-19T09:00:00Z"


def test_datetime_drops_microseconds() -> None:
    slot = _slot_ref(datetime(2026, 11, 19, 6, 0, 0, 987654), datetime(2026, 11, 19, 7))
    assert slot.model_dump(mode="json")["start_time"] == "2026-11-19T06:00:00Z"


def test_datetime_serialises_to_z_in_json_text() -> None:
    slot = _slot_ref(datetime(2026, 11, 19, 6), datetime(2026, 11, 19, 7))
    assert '"start_time":"2026-11-19T06:00:00Z"' in slot.model_dump_json()


def test_datetime_parses_z_input() -> None:
    slot = schemas.SlotRef.model_validate(
        {"id": 1, "start_time": "2026-11-19T06:00:00Z", "end_time": "2026-11-19T07:00:00Z"}
    )
    assert slot.model_dump(mode="json")["end_time"] == "2026-11-19T07:00:00Z"


# ---- nullability ----


def _booking_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": 5,
        "status": "active",
        "created_at": "2026-11-18T10:00:00Z",
        "cancelled_at": None,
        "cancellable": True,
        "lab": {"id": 1, "name": "Lab A"},
        "slot": {
            "id": 9,
            "start_time": "2026-11-19T06:00:00Z",
            "end_time": "2026-11-19T07:00:00Z",
        },
    }
    payload.update(overrides)
    return payload


def test_cancelled_at_null_is_accepted() -> None:
    booking = schemas.Booking.model_validate(_booking_payload())
    assert booking.cancelled_at is None
    assert booking.model_dump(mode="json")["cancelled_at"] is None


def test_cancelled_at_is_required_but_nullable() -> None:
    payload = _booking_payload()
    del payload["cancelled_at"]
    with pytest.raises(ValidationError):
        schemas.Booking.model_validate(payload)


def test_cancelled_at_value_serialises_with_z() -> None:
    booking = schemas.Booking.model_validate(
        _booking_payload(status="cancelled", cancelled_at="2026-11-18T11:30:00Z")
    )
    assert booking.status is schemas.BookingStatus.cancelled
    assert booking.model_dump(mode="json")["cancelled_at"] == "2026-11-18T11:30:00Z"


def test_admin_booking_cancelled_at_null_is_accepted() -> None:
    admin_booking = schemas.AdminBooking.model_validate(
        {
            "id": 1,
            "status": "active",
            "created_at": "2026-11-18T10:00:00Z",
            "cancelled_at": None,
            "slot": {
                "id": 9,
                "start_time": "2026-11-19T06:00:00Z",
                "end_time": "2026-11-19T07:00:00Z",
            },
            "user": {"id": 3, "student_number": "20250001"},
        }
    )
    assert admin_booking.cancelled_at is None


# ---- request models ----


def test_login_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        schemas.LoginRequest.model_validate(
            {"student_number": "1", "password": "x", "is_admin": True}
        )


def test_create_booking_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        schemas.CreateBookingRequest.model_validate({"slot_id": 1, "user_id": 2})


def test_create_closure_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        schemas.CreateClosureRequest.model_validate({"date": "2026-11-20", "reason": "x"})


def test_valid_requests_are_accepted() -> None:
    assert schemas.LoginRequest(student_number="20250001", password="pw").password == "pw"
    assert schemas.CreateBookingRequest(slot_id=3).slot_id == 3
    assert schemas.CreateClosureRequest.model_validate({"date": "2026-11-20"}).date.day == 20


@pytest.mark.parametrize(
    "payload",
    [
        {"student_number": "", "password": "x"},
        {"student_number": "1", "password": ""},
        {"student_number": "1" * 33, "password": "x"},
        {"student_number": "1", "password": "x" * 129},
        {"student_number": "1"},
        {"password": "x"},
    ],
)
def test_login_request_enforces_limits(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        schemas.LoginRequest.model_validate(payload)


def test_login_request_accepts_boundary_lengths() -> None:
    request = schemas.LoginRequest(student_number="1" * 32, password="x" * 128)
    assert len(request.student_number) == 32
    assert len(request.password) == 128


@pytest.mark.parametrize("payload", [{"date": "19-11-2026"}, {"date": "not a date"}, {}])
def test_create_closure_request_rejects_bad_date(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        schemas.CreateClosureRequest.model_validate(payload)


# ---- misc field rules ----


def test_login_response_token_type_is_bearer_only() -> None:
    payload = {
        "access_token": "abc",
        "token_type": "bearer",
        "expires_at": "2026-11-19T06:00:00Z",
        "user": {"id": 1, "student_number": "20250001", "is_admin": False},
    }
    response = schemas.LoginResponse.model_validate(payload)
    assert response.model_dump(mode="json") == payload
    with pytest.raises(ValidationError):
        schemas.LoginResponse.model_validate({**payload, "token_type": "basic"})


def test_numeric_minimums() -> None:
    with pytest.raises(ValidationError):
        schemas.Lab(id=1, name="Lab A", seats=0)
    with pytest.raises(ValidationError):
        schemas.Slot(
            id=1,
            start_time=datetime(2026, 11, 19, 6),
            end_time=datetime(2026, 11, 19, 7),
            seats=30,
            free_seats=-1,
            bookable=False,
        )
    with pytest.raises(ValidationError):
        schemas.ClosureCreated(
            id=1,
            lab_id=1,
            date="2026-11-20",
            created_at=datetime(2026, 11, 19, 6),
            cancelled_booking_count=-1,
        )


def test_error_details_accept_string_and_integer_locations() -> None:
    error = schemas.Error.model_validate(
        {
            "error": {
                "code": "validation_error",
                "message": "The request is not valid.",
                "details": [{"loc": ["body", "items", 0], "msg": "Field required"}],
            }
        }
    )
    assert error.error.code is schemas.ErrorCode.validation_error
    assert error.error.details is not None
    assert error.error.details[0].loc == ["body", "items", 0]


def test_unknown_error_code_is_rejected() -> None:
    with pytest.raises(ValidationError):
        schemas.Error.model_validate({"error": {"code": "nope", "message": "x"}})


def test_day_slots_and_closure_created_serialise_dates_and_instants() -> None:
    day = schemas.DaySlots.model_validate(
        {
            "lab": {"id": 1, "name": "Lab A", "seats": 30},
            "date": "2026-11-21",
            "day_status": "weekend",
            "slots": [],
        }
    )
    assert day.model_dump(mode="json")["date"] == "2026-11-21"
    closure = schemas.ClosureCreated(
        id=1,
        lab_id=2,
        date="2026-11-20",
        created_at=datetime(2026, 11, 19, 6, 0, 0),
        cancelled_booking_count=0,
    )
    assert closure.model_dump(mode="json") == {
        "id": 1,
        "lab_id": 2,
        "date": "2026-11-20",
        "created_at": "2026-11-19T06:00:00Z",
        "cancelled_booking_count": 0,
    }
