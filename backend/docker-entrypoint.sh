#!/bin/sh
# Container entrypoint: migrate, seed, then serve. Safe to run on every start:
# `alembic upgrade head` is a no-op when the database is current and the seed is idempotent.
# `set -e` stops the script (non-zero exit, uvicorn never starts) if a step fails.
set -eu

if [ -z "${JWT_SECRET:-}" ]; then
    echo "docker-entrypoint: JWT_SECRET is not set. Copy .env.example to .env and set it." >&2
    exit 1
fi

echo "docker-entrypoint: alembic upgrade head"
alembic upgrade head

echo "docker-entrypoint: python -m app.seed"
python -m app.seed

echo "docker-entrypoint: starting uvicorn on port 8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
