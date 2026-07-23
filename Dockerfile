FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY agents/gcrm-research-agent/   ./agents/gcrm-research-agent/
COPY agents/gcrm-enrichment-agent/ ./agents/gcrm-enrichment-agent/
COPY agents/gcrm-scout-agent/      ./agents/gcrm-scout-agent/
COPY agents/gcrm-outreach-agent/   ./agents/gcrm-outreach-agent/
COPY agents/gcrm-followup-agent/   ./agents/gcrm-followup-agent/
COPY agents/gcrm-opportunity-agent/ ./agents/gcrm-opportunity-agent/
COPY engcrm-interview-agent/       ./engcrm-interview-agent/
COPY gcrm/                         ./gcrm/
COPY scripts/                      ./scripts/
COPY pyproject.toml uv.lock ./

RUN uv sync --extra agents --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "gcrm.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
