🤖 Intake agent: spec v3

**Status:** Complete, 0 blocking questions, 0 non-blocking
**Plan written by:** mixed (client brief, project manager spec, developer tasks), for information only

## 1. Summary
A web-based booking system for the campus computer labs (Lab A, Lab B, Lab C), replacing the paper sign-up sheets on the lab doors. Students log in, see free 1-hour slots per lab, and book and cancel seats from their phones. Campus operations admins see who booked what and can close a lab for a date. The first release is a pilot with 20 students.

## 2. Users and roles
| Role | What they can do | Source |
|---|---|---|
| Student | Log in, see free slots per lab, book a slot, see own upcoming bookings (including cancelled ones, marked cancelled), cancel own bookings that haven't started | [plan], [answer] |
| Admin | Campus operations staff: see all bookings for a lab on a date, close a lab for a date. A user with `is_admin` set, logs in the same way as students. Admins can also use every student feature (book, cancel, see own bookings) | [plan], [answer] |

## 3. User stories
| ID | As a… I can… so that… | Priority | Source |
|---|---|---|---|
| US-1 | As a student, I can log in so the system knows who I am | Must | [plan] |
| US-2 | As a student, I can see the free slots for each lab for the next 7 days | Must | [plan] |
| US-3 | As a student, I can book a free 1-hour slot | Must | [plan], [answer] |
| US-4 | As a student, I can see my upcoming bookings | Must | [plan] |
| US-5 | As a student, I can cancel a booking that hasn't started yet, so someone else gets the seat | Must | [plan] |
| US-6 | As an admin, I can see all bookings for a lab on a given day (who booked what) | Must | [plan] |
| US-7 | As an admin, I can close a lab for a date, which cancels the bookings on it | Should | [plan] |

US-8 (email when an admin cancels) is Out of scope, see section 9.

## 4. Acceptance criteria
**US-1 Log in**
- A student can log in with their student number and a password [answer]
- Login returns a JWT used for later requests (POST /auth/login) [plan]
- The JWT is valid for 8 hours, configurable through an environment variable; there are no refresh tokens; logging out means the app discards its copy of the token [answer]
- Student accounts are pre-loaded for the pilot by a seed script; there is no self-registration [answer]
- Campus Operations supplies a CSV of student numbers and initial passwords; the CSV has an `is_admin` column (true/false) that creates admin accounts [answer]
- There is no password reset or change screen; admins re-seed if needed [answer]
- No student-number format check [answer]
- Admin endpoints return 403 to non-admin users [answer]

**US-2 See free slots**
- A student picks a lab and a date and sees the slots with the free seat count (GET /labs/{id}/slots?date=YYYY-MM-DD) [plan]
- Slots are shown for today plus the next 6 days [answer]
- Saturdays and Sundays show no slots [plan]
- A closed lab shows no free slots for the closed date [plan]
- Inactive labs are left out of the lab list (GET /labs) and their slots return 404 [answer]

**US-3 Book a slot**
- A student can't book a slot that is already full [plan]
- A student can't hold more than 2 bookings on the same day, counted across all labs [answer]
- A student can't hold two bookings in the same time slot, even in different labs [answer]
- A student can't book a slot in the past [plan]
- A slot can be booked only until its start time; once it has started it counts as the past [answer]
- A student can book only inside the window of today plus the next 6 days [answer]
- After booking, the slot shows one fewer free seat [plan]
- A double booking returns HTTP 409 [plan]
- Any logged-in user, including admins, can book [answer]

**US-4 My bookings**
- A student sees their own bookings whose slot hasn't ended yet, both active and cancelled, ordered by start time (GET /me/bookings) [plan], [answer]
- Cancelled bookings are shown marked as cancelled; no new field is added [answer]
- Past bookings (slot already ended) aren't shown [answer]

**US-5 Cancel**
- Cancelling frees the seat immediately [plan]
- A student can only cancel their own bookings [plan]
- A booking that has already started can't be cancelled [plan]
- The cancel button appears only on active bookings that haven't started [answer]

**US-6 Admin view**
- An admin sees all bookings for a lab on a given date, including who made each one (GET /admin/bookings?lab_id=&date=) [plan]
- The table includes cancelled bookings, each with a status (active or cancelled), so staff can see what a closure cancelled [answer]
- Non-admin users can't use admin functions (403) [answer]

**US-7 Close a lab (Should)**
- A closure applies to one lab and one date (POST /admin/labs/{id}/closures {date}) [plan]
- A closed lab shows no free slots for that date [plan]
- Existing bookings on that date are cancelled [plan]
- The closure date must be today or later, with no upper limit [answer]
- Closing the same lab and date twice returns 409 [answer]
- A closure cancels every active booking on that lab and date that hasn't started yet; bookings that have already started or finished are left alone [answer]
- A closure can't be undone (no reopen endpoint or button); bookings a closure cancelled stay cancelled [answer]

## 5. Business rules
- Labs are open 08:00 to 18:00, Monday to Friday [plan]
- Slots are 1 hour long, so 10 slots per lab per open day [plan], [answer]
- Labs: Lab A, Lab B, Lab C, each with exactly 30 seats, kept in the seed data so it can change [plan], [answer]
- Seats are counted, not assigned to a specific computer [plan]
- Students see and can book slots for today plus the next 6 days only [answer]
- Maximum per student: 2 bookings per day across all labs (2 hours a day) [answer]
- One booking per student per slot; no two bookings in the same time slot, even in different labs [answer]
- A full slot can't be booked; a booking in the past can't be made; a slot can be booked only until its start time [plan], [answer]
- A student can cancel only their own booking, and only before it starts [plan]
- A lab closure applies to one date, must be today or later, can only be made once per lab and date, hides all free slots for the date and cancels bookings on it that haven't started [plan], [answer]
- Public holidays are handled only by admins closing a lab for the date; there is no holiday calendar [answer]
- `is_active` takes a lab out of service completely; it is set only in the seed or database, with no screen for it [answer]
- Any logged-in user can use the student features; admin features also need `is_admin` [answer]
- JWT lifetime is 8 hours, configurable by environment variable, no refresh tokens [answer]
- Store all times in UTC [plan]
- Display times, and interpret opening hours and closure dates, in Africa/Johannesburg [answer]
- Pilot size is 20 students [plan]

## 6. Data
| Entity | Key fields | Source |
|---|---|---|
| labs | id, name, seats, is_active | [plan], [answer] |
| slots | id, lab_id, start_time, end_time (1-hour length) | [plan], [answer] |
| bookings | id, slot_id, user_id, created_at, cancelled_at | [plan] |
| users | id, student_number, password_hash, is_admin | [plan], [answer] |
| lab_closures | lab_id, date | [answer] |
| seed data | Lab A, Lab B, Lab C, 30 seats each | [plan], [answer] |
| pilot accounts | CSV with student number, initial password and `is_admin` (true/false), loaded by a seed script. The real CSV is not committed (it holds passwords); its path comes from an environment variable. A sample CSV with fake accounts is committed for development and tests | [answer] |
| migrations | Alembic | [plan] |

## 7. Screens
| Screen | Who uses it | What's on it | Source |
|---|---|---|---|
| Login | Student, Admin | Login form (student number and password) | [plan], [answer] |
| Book a slot | Student, Admin | Lab picker, date picker, slot grid with free seat counts | [plan], [answer] |
| My bookings | Student, Admin | Upcoming bookings (active and cancelled, cancelled marked), cancel button on active bookings that haven't started | [plan], [answer] |
| Admin bookings | Admin | Bookings table for a lab and date with a status per booking (active or cancelled), close lab button | [plan], [answer] |

All screens must work on a phone [plan].

## 8. Platform and stack
- Platform: responsive web app that works on phones [plan]
- Backend: FastAPI [plan], Python 3.12 [default]
- Database: SQLite via SQLAlchemy [plan]
- Frontend: React + Vite [plan], TypeScript [default]
- Login method: student number plus password, JWT (8 hours); pre-loaded accounts from a CSV; admins use the same login with `is_admin` [answer]
- JWT secret in a .env file [plan]
- Tests: pytest [plan], Playwright for end-to-end [default]
- Packaging: Docker + docker compose [plan]
- CI: GitHub Actions [default], pytest on every PR [plan]

## 9. Out of scope
- Payments [plan]
- Booking a specific computer [plan]
- Native mobile app, web only [plan]
- Deployment [default]
- Email notifications, including US-8 (email when an admin cancels a booking) [answer]
- Public holiday calendar [answer]
- Password reset or change screen [answer]
- Reopening a closed lab [answer]
- A screen for making a lab inactive [answer]

## 10. Open questions
None.

## 11. Changes since last version
Human replies on the issue: "Accept all suggested answers for Q12 to Q21". Q12 and Q13 came from spec v2; Q14 to Q21 came from the architect agent's comment. All are closed and their items are tagged [answer]:
- Q12: Campus Operations supplies a CSV of student numbers and initial passwords, loaded by a seed script; no password reset or change screen. The `[pending Q12]` tag is removed from the seed data row.
- Q13: a slot can be booked only until its start time.
- Q14: the same CSV has an `is_admin` column; the real CSV isn't committed and its path comes from an environment variable; a sample CSV with fake accounts is committed.
- Q15: closure date must be today or later with no upper limit; closing the same lab and date twice returns 409; a closure cancels only active bookings that haven't started.
- Q16: closures can't be undone.
- Q17: any logged-in user can use the student features, admins included; Book a slot and My bookings screens now list Admin as a user.
- Q18: My bookings lists active and cancelled bookings whose slot hasn't ended, ordered by start time.
- Q19: the admin bookings table includes cancelled bookings with a status.
- Q20: `is_active` is set only in the seed or database; inactive labs are left out of the lab list and their slots return 404.
- Q21: JWT valid 8 hours, configurable by environment variable, no refresh tokens.
- Added to Out of scope: password reset or change screen, reopening a closed lab, a screen for making a lab inactive.
- Status stays Complete; there are now 0 open questions (was 2 non-blocking).
