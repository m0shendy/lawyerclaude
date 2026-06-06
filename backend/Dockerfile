# Lawyer Office AI Engine — FastAPI API + background workers (one image, two entrypoints).
# Workers override the command in docker-compose:
#   python -m workers.pipeline_worker / python -m workers.scheduler_worker
FROM python:3.12-slim

# uv — fast installer (no pip cache, reproducible installs)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv/backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Project metadata first for layer caching, then the code.
COPY pyproject.toml ./
COPY app ./app
COPY workers ./workers

RUN uv pip install --system .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
