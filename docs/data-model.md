# Data model

Source: `docs/spec.md` (spec v3 of issue #6). Rule numbers ("rule 5.N") mean the Nth bullet of spec section 5; the full list is in `docs/architecture.md`.

Database: SQLite through SQLAlchemy 2.x, schema managed by Alembic (spec section 8). One initial migration creates everything below.

## Conventions

- **Times are stored as naive UTC** (`DATETIME` without offset) (rule 5.15). SQLite has no time zone type, so the rule is: every value written is UTC, and every value read is treated as UTC. The API layer adds the `Z` when serialising (see `docs/api.yaml`).
- **Dates are stored as `DATE`** and are calendar dates in Africa/Johannesburg (rule 5.16). Only `lab_closures.date` is a date column.
- Primary keys are `INTEGER` autoincrement `id`.
- Foreign keys are enforced: the engine runs `PRAGMA foreign_keys = ON` on every connection (SQLite has them off by default).
- No row is ever hard-deleted by the app. Bookings are cancelled by setting `cancelled_at` (spec section 6).

## Tables

### `users`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INTEGER | no | autoincrement | PK |
| student_number | VARCHAR(32) | no | | Login name. Stored exactly as in the CSV; no format check (US-1) |
| password_hash | VARCHAR(255) | no | | bcrypt hash, never the plain password |
| is_admin | BOOLEAN | no | false | Admin features need this (rule 5.13) |
| created_at | DATETIME | no | now (UTC) | |

Constraints and indexes:
- `uq_users_student_number` UNIQUE (`student_number`): one account per student number, and the seed upserts by it (US-1).

### `labs`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INTEGER | no | autoincrement | PK |
| name | VARCHAR(50) | no | | "Lab A", "Lab B", "Lab C" |
| seats | INTEGER | no | | Number of computers; seats are counted, not assigned (rule 5.4) |
| is_active | BOOLEAN | no | true | false = out of service completely; set only by seed or directly in the database (rule 5.12) |

Constraints and indexes:
- `uq_labs_name` UNIQUE (`name`): the seed upserts labs by name (rule 5.3).
- `ck_labs_seats_positive` CHECK (`seats > 0`) (rule 5.3).

### `slots`

One row per lab per 1-hour period. Rows are created on demand by the backend when an open date is first requested (see `GET /labs/{lab_id}/slots`), never for Saturdays or Sundays, and never by the seed.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INTEGER | no | autoincrement | PK |
| lab_id | INTEGER | no | | FK -> `labs.id` |
| start_time | DATETIME | no | | UTC. Local 08:00, 09:00, ..., 17:00 Africa/Johannesburg (rules 5.1, 5.2, 5.16) |
| end_time | DATETIME | no | | UTC. Always `start_time + 1 hour` (rule 5.2) |

Constraints and indexes:
- `fk_slots_lab_id` FOREIGN KEY (`lab_id`) REFERENCES `labs(id)`.
- `uq_slots_lab_start` UNIQUE (`lab_id`, `start_time`): one slot per lab per hour, so creating slots on demand is idempotent (rule 5.2).
- `ck_slots_end_after_start` CHECK (`end_time > start_time`).
- `ix_slots_start_time` INDEX (`start_time`): finds slots at the same time in other labs, for the overlap check (rule 5.7).

### `bookings`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INTEGER | no | autoincrement | PK |
| slot_id | INTEGER | no | | FK -> `slots.id` |
| user_id | INTEGER | no | | FK -> `users.id` |
| created_at | DATETIME | no | now (UTC) | |
| cancelled_at | DATETIME | yes | NULL | NULL = active; set = cancelled, by the student (US-5) or by a closure (US-7). Status is derived from this; there is no status column (spec US-4: "no new field") |

Constraints and indexes:
- `fk_bookings_slot_id` FOREIGN KEY (`slot_id`) REFERENCES `slots(id)`.
- `fk_bookings_user_id` FOREIGN KEY (`user_id`) REFERENCES `users(id)`.
- `uq_bookings_active_user_slot` UNIQUE (`user_id`, `slot_id`) **WHERE `cancelled_at IS NULL`** (partial unique index; SQLAlchemy `Index(..., unique=True, sqlite_where=...)`): at most one *active* booking per student per slot (rule 5.7). It is partial so a student can re-book a slot after cancelling it.
- `ix_bookings_slot_id` INDEX (`slot_id`): counting active bookings per slot for free seats (rules 5.4, 5.8).
- `ix_bookings_user_id` INDEX (`user_id`): My bookings, daily limit and overlap checks (US-4, rules 5.6, 5.7).

### `lab_closures`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INTEGER | no | autoincrement | PK |
| lab_id | INTEGER | no | | FK -> `labs.id` |
| date | DATE | no | | Calendar date in Africa/Johannesburg (rule 5.16) |
| created_at | DATETIME | no | now (UTC) | |

Constraints and indexes:
- `fk_lab_closures_lab_id` FOREIGN KEY (`lab_id`) REFERENCES `labs(id)`.
- `uq_lab_closures_lab_date` UNIQUE (`lab_id`, `date`): a lab can be closed only once per date; a second attempt is 409 `closure_exists` (rule 5.10). There is no delete path: closures can't be undone (spec section 9).

## Rules enforced in code, not by constraints

These need data from several rows or the current time, so the backend services enforce them (see the check order in `docs/api.yaml`):

| Rule | Where |
|---|---|
| Opening hours and 1-hour slots (5.1, 5.2) | Slot generation, `GET /labs/{lab_id}/slots` |
| Booking window, today + 6 days (5.5) | `GET /labs/{lab_id}/slots`, `POST /bookings` |
| Max 2 active bookings per user per local date, all labs (5.6) | `POST /bookings` |
| No two active bookings at the same `start_time` in different labs (5.7) | `POST /bookings` |
| Capacity: active bookings for a slot < `labs.seats` (5.4, 5.8) | `POST /bookings` |
| No booking once the slot has started (5.8) | `POST /bookings` |
| Cancel own booking only, and only before it starts (5.9) | `DELETE /bookings/{booking_id}` |
| Closure date today or later; cancels only active, not-started bookings (5.10) | `POST /admin/labs/{lab_id}/closures` |
| Inactive labs hidden and 404 (5.12) | `GET /labs`, slots, bookings, admin endpoints |

Known limit: SQLite serialises writes, but the capacity and daily-limit checks are read-then-write. The booking service runs checks and insert in one transaction; at pilot scale (20 students, rule 5.17) the remaining race is accepted.

## Seed data

`python -m app.seed` (run from `backend/`) is idempotent: running it twice changes nothing the second time.

**Labs** (rule 5.3), upserted by `name`. Re-running the seed sets `seats` and `is_active` to these values, so the seat count can be changed by editing the seed:

| name | seats | is_active |
|---|---|---|
| Lab A | 30 | true |
| Lab B | 30 | true |
| Lab C | 30 | true |

**Accounts** (US-1, spec section 6 "pilot accounts"), from the CSV at `ACCOUNTS_CSV_PATH`:

- Header row exactly `student_number,password,is_admin`. `is_admin` is `true` or `false` (case-insensitive).
- Upserted by `student_number`: new rows are inserted; existing users get their `password_hash` and `is_admin` replaced (this is how admins "re-seed" a password, spec US-1). Users not in the CSV are left alone.
- Validation happens before any write. A row with an empty `student_number` or `password`, an `is_admin` that isn't true/false, or a duplicate `student_number` makes the seed exit non-zero, naming the line, with nothing written.
- The real CSV is never committed. A sample with fake accounts is committed at `backend/seed_data/accounts.sample.csv` and is the default path. Its exact content (tests and the frontend mock use these):

```csv
student_number,password,is_admin
20260001,student-pass-1,false
20260002,student-pass-2,false
20260003,student-pass-3,false
90000001,admin-pass-1,true
```
