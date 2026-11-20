"""Idempotent seed: labs and pilot accounts (``python -m app.seed``, run from ``backend/``).

Labs are upserted by name. Accounts come from the CSV at ``ACCOUNTS_CSV_PATH`` and are
upserted by student number. The whole CSV is validated before anything is written.
"""

import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers the tables)
from app.db import SessionLocal
from app.models import Lab, User
from app.passwords import hash_password, verify_password

DEFAULT_ACCOUNTS_CSV_PATH = "seed_data/accounts.sample.csv"
CSV_HEADER = ["student_number", "password", "is_admin"]

# Rule 5.3: Lab A, Lab B, Lab C, 30 seats each. Edit here to change the seat count.
LABS = [
    {"name": "Lab A", "seats": 30, "is_active": True},
    {"name": "Lab B", "seats": 30, "is_active": True},
    {"name": "Lab C", "seats": 30, "is_active": True},
]

STUDENT_NUMBER_MAX_LENGTH = 32  # users.student_number is VARCHAR(32)
PASSWORD_MAX_BYTES = 72  # bcrypt cannot hash more than 72 bytes


class SeedError(Exception):
    """The accounts CSV is invalid. The message names the CSV line."""


@dataclass(frozen=True)
class AccountRow:
    line: int
    student_number: str
    password: str
    is_admin: bool


@dataclass(frozen=True)
class SeedResult:
    labs_upserted: int
    accounts_created: int
    accounts_updated: int

    def summary(self) -> str:
        return (
            f"Seed complete: {self.labs_upserted} labs upserted, "
            f"{self.accounts_created} accounts created, {self.accounts_updated} accounts updated"
        )


def get_accounts_csv_path() -> Path:
    """ACCOUNTS_CSV_PATH from the environment (relative paths are relative to the working directory)."""
    return Path(os.environ.get("ACCOUNTS_CSV_PATH") or DEFAULT_ACCOUNTS_CSV_PATH)


def read_accounts(path: Path) -> list[AccountRow]:
    """Read and validate every row. Raises SeedError naming the CSV line on the first problem."""
    try:
        handle = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise SeedError(f"cannot read accounts CSV {path}: {exc.strerror or exc}") from exc

    with handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise SeedError("line 1: the CSV is empty, expected header row 'student_number,password,is_admin'")
        except (csv.Error, UnicodeDecodeError) as exc:
            raise SeedError(f"line {reader.line_num}: {exc}") from exc
        if header != CSV_HEADER:
            raise SeedError(
                f"line 1: header must be exactly 'student_number,password,is_admin', got '{','.join(header)}'"
            )

        rows: list[AccountRow] = []
        first_seen: dict[str, int] = {}
        while True:
            try:
                fields = next(reader)
            except StopIteration:
                break
            except (csv.Error, UnicodeDecodeError) as exc:
                raise SeedError(f"line {reader.line_num}: {exc}") from exc
            line = reader.line_num
            row = _validate_row(line, fields)
            if row.student_number in first_seen:
                raise SeedError(
                    f"line {line}: duplicate student_number '{row.student_number}' "
                    f"(first used on line {first_seen[row.student_number]})"
                )
            first_seen[row.student_number] = line
            rows.append(row)
    return rows


def _validate_row(line: int, fields: list[str]) -> AccountRow:
    if len(fields) != len(CSV_HEADER):
        raise SeedError(f"line {line}: expected {len(CSV_HEADER)} columns, got {len(fields)}")
    student_number, password, is_admin_raw = fields
    student_number = student_number.strip()
    if not student_number:
        raise SeedError(f"line {line}: student_number is empty")
    if len(student_number) > STUDENT_NUMBER_MAX_LENGTH:
        raise SeedError(f"line {line}: student_number is longer than {STUDENT_NUMBER_MAX_LENGTH} characters")
    if not password:
        raise SeedError(f"line {line}: password is empty")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise SeedError(f"line {line}: password is longer than {PASSWORD_MAX_BYTES} bytes (the bcrypt limit)")
    flag = is_admin_raw.strip().lower()
    if flag not in ("true", "false"):
        raise SeedError(f"line {line}: is_admin must be 'true' or 'false', got '{is_admin_raw}'")
    return AccountRow(line, student_number, password, flag == "true")


def upsert_labs(session: Session) -> int:
    """Upsert the labs by name, resetting seats and is_active. Returns the number of labs upserted."""
    existing = {lab.name: lab for lab in session.scalars(select(Lab))}
    for spec in LABS:
        lab = existing.get(spec["name"])
        if lab is None:
            session.add(Lab(**spec))
        else:
            lab.seats = spec["seats"]
            lab.is_active = spec["is_active"]
    return len(LABS)


def upsert_accounts(session: Session, rows: list[AccountRow]) -> tuple[int, int]:
    """Upsert accounts by student number. Returns (created, updated).

    bcrypt hashes are salted, so an existing user whose password already matches and whose
    is_admin is unchanged is left alone (and not counted), which keeps a second run a no-op.
    """
    existing = {user.student_number: user for user in session.scalars(select(User))}
    created = updated = 0
    for row in rows:
        user = existing.get(row.student_number)
        if user is None:
            session.add(
                User(
                    student_number=row.student_number,
                    password_hash=hash_password(row.password),
                    is_admin=row.is_admin,
                )
            )
            created += 1
        elif user.is_admin != row.is_admin or not verify_password(row.password, user.password_hash):
            user.password_hash = hash_password(row.password)
            user.is_admin = row.is_admin
            updated += 1
    return created, updated


def seed(session: Session, rows: list[AccountRow]) -> SeedResult:
    """Write labs and accounts in one transaction. ``rows`` must already be validated."""
    try:
        labs = upsert_labs(session)
        created, updated = upsert_accounts(session, rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SeedResult(labs, created, updated)


def main() -> int:
    try:
        rows = read_accounts(get_accounts_csv_path())
    except SeedError as exc:
        print(f"Seed failed, nothing was written: {exc}", file=sys.stderr)
        return 1
    with SessionLocal() as session:
        result = seed(session, rows)
    print(result.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
