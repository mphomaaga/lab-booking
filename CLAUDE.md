# lab-booking

This repo is a test bed for a multi-agent pipeline: a project plan goes in, a team of agents turns it into a spec, then issues, then working code. The app (campus lab booking) is test material. The pipeline is what's being tested.

## Pipeline

1. **Intake:** a plan arrives as an issue labelled `plan`. The intake agent turns it into a spec (see the `spec` skill) and asks about anything missing.
2. **Architect:** turns an approved spec into an API contract and issues on the board.
3. **Build:** db, backend, frontend and infra agents work Ready cards.
4. **Verify:** reviewer, CI and QA check every PR.

A human approves at every gate. Agents never merge.

## The board

The board is GitHub Projects board 2 (Agent Pipeline). Always use the `board-ops` skill to read or change it. Never call `gh project` directly.

## House defaults

Use these unless the plan, or an answer from a human, says otherwise. When you use one, mark it as a default so a human can see it wasn't in the plan.

| Area | Default |
|---|---|
| Backend | Python 3.12, FastAPI |
| Database | SQLite via SQLAlchemy, migrations with Alembic |
| Frontend | React + Vite, TypeScript |
| Platform | Responsive web app that works on phones. No native app. |
| Tests | pytest for the backend, Playwright for end-to-end |
| Packaging | Docker + docker compose |
| CI | GitHub Actions, tests on every PR |
| Deployment | Out of scope for the prototype |
| Time zone | Store UTC; display Africa/Johannesburg |

There is **no default for login/authentication**: always ask. There is **no email or SMS service**: flag any feature that needs one.

## Rules for every agent

- Stay inside your role. Don't edit files outside your area.
- Never invent requirements. If something isn't in the plan, an answer or the house defaults, ask.
- Start every comment you post with a header naming your role, for example `🤖 Intake agent`. Local agents post under a human's GitHub account, so the header is how people tell agent comments apart.
- Branches: `<role>/issue-<number>-<short-slug>`.
