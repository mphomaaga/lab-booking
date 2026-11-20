"""Tests for ``python -m app.seed``. Every test uses its own temporary SQLite database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import seed as seed_module
from app.models import Lab, User
from app.passwords import verify_password
from app.seed import SeedError, read_accounts, seed

BACKEND_DIR = Path(__file__).resolve().parents[2]
SAMPLE_CSV = BACKEND_DIR / "seed_data" / "accounts.sample.csv"

SAMPLE_CONTENT = """student_number,password,is_admin
20260001,student-pass-1,false
20260002,student-pass-2,false
20260003,student-pass-3,false
90000001,admin-pass-1,true
"""


def write_csv(tmp_path: Path, body: str, header: str = "student_number,password,is_admin") -> Path:
    path = tmp_path / "accounts.csv"
    path.write_text(f"{header}\n{body}", encoding="utf-8")
    return path


def run_seed(session: Session, path: Path):
    return seed(session, read_accounts(path))


def snapshot(session: Session):
    labs = [(lab.name, lab.seats, lab.is_active) for lab in session.scalars(select(Lab).order_by(Lab.id))]
    users = [
        (u.id, u.student_number, u.password_hash, u.is_admin) for u in session.scalars(select(User).order_by(User.id))
    ]
    return labs, users


# --- sample CSV ---------------------------------------------------------------------------


def test_sample_csv_matches_contract():
    assert SAMPLE_CSV.read_text(encoding="utf-8") == SAMPLE_CONTENT


def test_sample_csv_seeds_the_documented_accounts(db_session):
    result = run_seed(db_session, SAMPLE_CSV)
    assert (result.accounts_created, result.accounts_updated) == (4, 0)
    users = {u.student_number: u for u in db_session.scalars(select(User))}
    assert set(users) == {"20260001", "20260002", "20260003", "90000001"}
    assert [users[n].is_admin for n in ("20260001", "20260002", "20260003", "90000001")] == [
        False,
        False,
        False,
        True,
    ]
    assert verify_password("student-pass-1", users["20260001"].password_hash)
    assert verify_password("admin-pass-1", users["90000001"].password_hash)


# --- labs ---------------------------------------------------------------------------------


def test_labs_are_created(db_session):
    result = run_seed(db_session, SAMPLE_CSV)
    assert result.labs_upserted == 3
    labs = db_session.scalars(select(Lab).order_by(Lab.name)).all()
    assert [(lab.name, lab.seats, lab.is_active) for lab in labs] == [
        ("Lab A", 30, True),
        ("Lab B", 30, True),
        ("Lab C", 30, True),
    ]


def test_rerun_resets_lab_seats_and_is_active_but_keeps_ids(db_session):
    run_seed(db_session, SAMPLE_CSV)
    lab_a = db_session.scalars(select(Lab).where(Lab.name == "Lab A")).one()
    lab_a_id = lab_a.id
    lab_a.seats = 12
    lab_a.is_active = False
    db_session.commit()

    run_seed(db_session, SAMPLE_CSV)

    lab_a = db_session.scalars(select(Lab).where(Lab.name == "Lab A")).one()
    assert (lab_a.id, lab_a.seats, lab_a.is_active) == (lab_a_id, 30, True)
    assert len(db_session.scalars(select(Lab)).all()) == 3


def test_other_labs_are_left_alone(db_session):
    db_session.add(Lab(name="Lab D", seats=5, is_active=False))
    db_session.commit()
    run_seed(db_session, SAMPLE_CSV)
    lab_d = db_session.scalars(select(Lab).where(Lab.name == "Lab D")).one()
    assert (lab_d.seats, lab_d.is_active) == (5, False)


# --- accounts: parsing --------------------------------------------------------------------


def test_is_admin_is_case_insensitive(tmp_path, db_session):
    path = write_csv(tmp_path, "1001,pw-one,TRUE\n1002,pw-two,False\n1003,pw-three,tRuE\n")
    run_seed(db_session, path)
    flags = {u.student_number: u.is_admin for u in db_session.scalars(select(User))}
    assert flags == {"1001": True, "1002": False, "1003": True}


def test_passwords_are_hashed(tmp_path, db_session):
    run_seed(db_session, write_csv(tmp_path, "1001,plain-secret,false\n"))
    user = db_session.scalars(select(User)).one()
    assert user.password_hash != "plain-secret"
    assert user.password_hash.startswith("$2")
    assert verify_password("plain-secret", user.password_hash)


def test_no_row_limit(tmp_path, db_session):
    body = "".join(f"2026{n:04d},pass-{n},false\n" for n in range(1, 51))
    result = run_seed(db_session, write_csv(tmp_path, body))
    assert result.accounts_created == 50
    assert len(db_session.scalars(select(User)).all()) == 50


def test_header_only_csv_seeds_labs_and_no_accounts(tmp_path, db_session):
    result = run_seed(db_session, write_csv(tmp_path, ""))
    assert (result.labs_upserted, result.accounts_created, result.accounts_updated) == (3, 0, 0)


# --- accounts: upsert ---------------------------------------------------------------------


def test_existing_user_gets_password_and_is_admin_replaced(tmp_path, db_session):
    run_seed(db_session, write_csv(tmp_path, "1001,old-pass,false\n"))
    old_id = db_session.scalars(select(User)).one().id

    result = run_seed(db_session, write_csv(tmp_path, "1001,new-pass,true\n"))

    assert (result.accounts_created, result.accounts_updated) == (0, 1)
    user = db_session.scalars(select(User)).one()
    assert user.id == old_id
    assert user.is_admin is True
    assert verify_password("new-pass", user.password_hash)
    assert not verify_password("old-pass", user.password_hash)


def test_password_only_change_counts_as_update(tmp_path, db_session):
    run_seed(db_session, write_csv(tmp_path, "1001,old-pass,false\n"))
    result = run_seed(db_session, write_csv(tmp_path, "1001,new-pass,false\n"))
    assert (result.accounts_created, result.accounts_updated) == (0, 1)


def test_users_not_in_csv_are_untouched(tmp_path, db_session):
    run_seed(db_session, write_csv(tmp_path, "1001,pw-one,false\n1002,pw-two,true\n"))
    before = {u.student_number: (u.id, u.password_hash, u.is_admin) for u in db_session.scalars(select(User))}

    run_seed(db_session, write_csv(tmp_path, "1003,pw-three,false\n"))

    after = {u.student_number: (u.id, u.password_hash, u.is_admin) for u in db_session.scalars(select(User))}
    assert set(after) == {"1001", "1002", "1003"}
    assert after["1001"] == before["1001"]
    assert after["1002"] == before["1002"]


# --- idempotency and summary --------------------------------------------------------------


def test_second_run_changes_nothing(db_session):
    first = run_seed(db_session, SAMPLE_CSV)
    before = snapshot(db_session)

    second = run_seed(db_session, SAMPLE_CSV)

    assert (first.accounts_created, first.accounts_updated) == (4, 0)
    assert (second.accounts_created, second.accounts_updated) == (0, 0)
    assert snapshot(db_session) == before


def test_summary_line():
    result = seed_module.SeedResult(labs_upserted=3, accounts_created=4, accounts_updated=1)
    summary = result.summary()
    assert "\n" not in summary
    assert "3 labs upserted" in summary
    assert "4 accounts created" in summary
    assert "1 accounts updated" in summary


# --- validation ---------------------------------------------------------------------------

BAD_ROWS = [
    ("empty student_number", ",pw,false\n", "line 2", "student_number is empty"),
    ("blank student_number", "   ,pw,false\n", "line 2", "student_number is empty"),
    ("empty password", "1001,,false\n", "line 2", "password is empty"),
    ("bad is_admin", "1001,pw,yes\n", "line 2", "is_admin"),
    ("empty is_admin", "1001,pw,\n", "line 2", "is_admin"),
    ("too few columns", "1001,pw\n", "line 2", "columns"),
    ("too many columns", "1001,pw,false,extra\n", "line 2", "columns"),
    ("duplicate", "1001,pw,false\n1001,pw2,true\n", "line 3", "duplicate"),
    ("over-long password", "1001," + "x" * 73 + ",false\n", "line 2", "72 bytes"),
    ("over-long multibyte password", "1001," + "é" * 37 + ",false\n", "line 2", "72 bytes"),
    ("over-long student_number", "1" * 33 + ",pw,false\n", "line 2", "student_number"),
]


@pytest.mark.parametrize(("label", "body", "line", "fragment"), BAD_ROWS, ids=[b[0] for b in BAD_ROWS])
def test_bad_row_is_rejected_naming_the_line(tmp_path, label, body, line, fragment):
    with pytest.raises(SeedError) as excinfo:
        read_accounts(write_csv(tmp_path, body))
    assert line in str(excinfo.value)
    assert fragment in str(excinfo.value)


def test_password_of_exactly_72_bytes_is_accepted(tmp_path, db_session):
    password = "x" * 72
    run_seed(db_session, write_csv(tmp_path, f"1001,{password},false\n"))
    user = db_session.scalars(select(User)).one()
    assert verify_password(password, user.password_hash)


def test_error_names_the_line_of_a_later_bad_row(tmp_path):
    body = "1001,pw,false\n1002,pw,false\n1003,pw,maybe\n"
    with pytest.raises(SeedError, match="line 4"):
        read_accounts(write_csv(tmp_path, body))


@pytest.mark.parametrize(
    "header",
    [
        "student_number,password",
        "student_number,password,is_admin,extra",
        "password,student_number,is_admin",
        "Student_Number,Password,Is_Admin",
    ],
)
def test_wrong_header_is_rejected(tmp_path, header):
    with pytest.raises(SeedError, match="line 1"):
        read_accounts(write_csv(tmp_path, "1001,pw,false\n", header=header))


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "accounts.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(SeedError, match="line 1"):
        read_accounts(path)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(SeedError, match="cannot read"):
        read_accounts(tmp_path / "nope.csv")


# --- command line: exit codes and the database stays unchanged ----------------------------


def run_cli(db_url: str, csv_path: Path | None):
    env = {**os.environ, "DATABASE_URL": db_url}
    env.pop("ACCOUNTS_CSV_PATH", None)
    if csv_path is not None:
        env["ACCOUNTS_CSV_PATH"] = str(csv_path)
    return subprocess.run(
        [sys.executable, "-m", "app.seed"], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=False
    )


def test_cli_seeds_and_prints_one_line_summary(db_url, db_engine, db_session):
    proc = run_cli(db_url, SAMPLE_CSV)
    assert proc.returncode == 0, proc.stderr
    assert len(proc.stdout.strip().splitlines()) == 1
    assert "3 labs upserted" in proc.stdout
    assert "4 accounts created" in proc.stdout
    assert "0 accounts updated" in proc.stdout
    assert len(db_session.scalars(select(Lab)).all()) == 3


def test_cli_uses_sample_csv_by_default(db_url, db_engine, db_session):
    proc = run_cli(db_url, None)
    assert proc.returncode == 0, proc.stderr
    assert len(db_session.scalars(select(User)).all()) == 4


def test_cli_second_run_reports_no_changes(db_url, db_engine):
    run_cli(db_url, SAMPLE_CSV)
    proc = run_cli(db_url, SAMPLE_CSV)
    assert proc.returncode == 0, proc.stderr
    assert "0 accounts created, 0 accounts updated" in proc.stdout


def test_cli_invalid_csv_exits_non_zero_and_writes_nothing(tmp_path, db_url, db_engine, db_session):
    # Existing data that a partial run could have changed.
    run_cli(db_url, SAMPLE_CSV)
    db_session.expire_all()
    before = snapshot(db_session)
    bad = write_csv(tmp_path, "20260001,changed-pass,true\n20269999,new-pass,false\n20260001,dup,false\n")

    proc = run_cli(db_url, bad)

    assert proc.returncode != 0
    assert "line 4" in proc.stderr
    db_session.expire_all()
    assert snapshot(db_session) == before


def test_cli_invalid_csv_on_empty_database_creates_no_rows(tmp_path, db_url, db_engine, db_session):
    proc = run_cli(db_url, write_csv(tmp_path, "1001,pw,false\n1002,,false\n"))
    assert proc.returncode != 0
    assert "line 3" in proc.stderr
    assert db_session.scalars(select(Lab)).all() == []
    assert db_session.scalars(select(User)).all() == []


def test_cli_over_long_password_exits_cleanly(tmp_path, db_url, db_engine, db_session):
    proc = run_cli(db_url, write_csv(tmp_path, "1001," + "x" * 100 + ",false\n"))
    assert proc.returncode != 0
    assert "Traceback" not in proc.stderr
    assert "line 2" in proc.stderr
    assert db_session.scalars(select(User)).all() == []


# --- error output never contains CSV content (passwords) ----------------------------------

SENTINEL = "S3ntinel-PW-do-not-print"
HEADER = "student_number,password,is_admin"

# (id, whole file as bytes, text that must appear in the error). Each file puts SENTINEL in a
# cell that the seed treats as something else, or in a row that is rejected for another reason.
LEAK_CASES = [
    # The two reproductions from the review: headerless file, and password/is_admin swapped.
    ("headerless", f"20260001,{SENTINEL},false\n20260002,pw-two,false\n".encode(), "line 1"),
    ("headerless-sentinel-first-cell", f"{SENTINEL},pw-one,false\n".encode(), "line 1"),
    ("swapped-password-and-is_admin", f"{HEADER}\n20260001,true,{SENTINEL}\n".encode(), "line 2"),
    ("swapped-on-a-later-row", f"{HEADER}\n1001,pw,false\n1002,pw2,true\n1003,true,{SENTINEL}\n".encode(), "line 4"),
    ("is_admin-cell-is-the-password", f"{HEADER}\n1001,pw,{SENTINEL}\n".encode(), "line 2"),
    # Header variants.
    ("header-columns-reordered", f"password,student_number,is_admin,{SENTINEL}\n".encode(), "line 1"),
    ("header-is-one-sentinel-cell", f"{SENTINEL}\n".encode(), "line 1"),
    # Duplicates, with student_number and password swapped so the "student number" is a password.
    ("duplicate-with-swapped-columns", f"{HEADER}\n{SENTINEL},1001,false\n{SENTINEL},1002,true\n".encode(), "line 3"),
    # Other row errors with the sentinel somewhere in the row.
    ("too-many-columns", f"{HEADER}\n1001,{SENTINEL},false,extra\n".encode(), "line 2"),
    ("too-few-columns", f"{HEADER}\n1001,{SENTINEL}\n".encode(), "line 2"),
    ("empty-student_number", f"{HEADER}\n,{SENTINEL},false\n".encode(), "line 2"),
    ("empty-password-after-sentinel-row", f"{HEADER}\n1001,{SENTINEL},false\n1002,,false\n".encode(), "line 3"),
    ("over-long-password", f"{HEADER}\n1001,{SENTINEL}{'x' * 80},false\n".encode(), "line 2"),
    ("over-long-student_number", f"{HEADER}\n{SENTINEL}{'1' * 40},pw,false\n".encode(), "line 2"),
    ("unterminated-quote", f'{HEADER}\n1001,"{SENTINEL},false\n'.encode(), "line"),
    ("bad-utf8", f"{HEADER}\n1001,{SENTINEL}\xe9,false\n".encode("latin-1"), "line 2"),
    ("bad-utf8-in-first-row", b"\xff\xfe" + SENTINEL.encode() + b",pw,false\n", "line 1"),
]


def write_bytes(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "accounts.csv"
    path.write_bytes(content)
    return path


@pytest.mark.parametrize(("content", "expected"), [c[1:] for c in LEAK_CASES], ids=[c[0] for c in LEAK_CASES])
def test_error_text_never_contains_csv_content(tmp_path, content, expected):
    with pytest.raises(SeedError) as excinfo:
        read_accounts(write_bytes(tmp_path, content))
    message = str(excinfo.value)
    assert SENTINEL not in message
    assert expected in message  # still tells the operator where to look


@pytest.mark.parametrize(("content", "expected"), [c[1:] for c in LEAK_CASES], ids=[c[0] for c in LEAK_CASES])
def test_cli_stderr_and_stdout_never_contain_csv_content(tmp_path, db_url, db_engine, content, expected):
    proc = run_cli(db_url, write_bytes(tmp_path, content))
    assert proc.returncode != 0
    assert SENTINEL not in proc.stderr
    assert SENTINEL not in proc.stdout
    assert "Traceback" not in proc.stderr
    assert expected in proc.stderr


def test_header_and_is_admin_messages_still_say_what_was_expected(tmp_path):
    with pytest.raises(SeedError) as header_error:
        read_accounts(write_bytes(tmp_path, f"20260001,{SENTINEL},false\n".encode()))
    assert "student_number,password,is_admin" in str(header_error.value)

    with pytest.raises(SeedError) as flag_error:
        read_accounts(write_bytes(tmp_path, f"{HEADER}\n20260001,true,{SENTINEL}\n".encode()))
    assert "line 2" in str(flag_error.value)
    assert "is_admin" in str(flag_error.value)
    assert "'true' or 'false'" in str(flag_error.value)


def test_duplicate_error_names_both_lines(tmp_path):
    with pytest.raises(SeedError) as excinfo:
        read_accounts(write_csv(tmp_path, "1001,pw,false\n1002,pw,false\n1001,pw2,true\n"))
    message = str(excinfo.value)
    assert "line 4" in message
    assert "line 2" in message
