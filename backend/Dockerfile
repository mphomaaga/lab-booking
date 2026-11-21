# Backend image: FastAPI app on Python 3.12. Build context is backend/ (see docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the app package from pyproject.toml, without the [dev] extra.
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# Migrations, seed script and the sample accounts CSV (the real CSV is excluded by
# .dockerignore and is mounted at run time instead).
COPY alembic.ini ./
COPY alembic ./alembic
COPY seed_data ./seed_data
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Run as a non-root user. /data is the mount point of the db-data volume.
RUN useradd --system --no-create-home --uid 10001 app \
    && mkdir /data \
    && chown app:app /data
USER app

# No secrets here: JWT_SECRET and the rest come from the environment (docker compose .env).
ENV DATABASE_URL=sqlite:////data/lab_booking.db

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
