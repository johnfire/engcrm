FROM python:3.13-alpine@sha256:1e1f6334529d1fb26a2ef619d7cffb30a7c7d7cc1cc7338ebee283a58d1aeaca AS builder

WORKDIR /app

RUN apk add --no-cache build-base postgresql-dev linux-headers

COPY --from=ghcr.io/astral-sh/uv:latest@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /usr/local/bin/uv

COPY agents/gcrm-research-agent/   ./agents/gcrm-research-agent/
COPY agents/gcrm-enrichment-agent/ ./agents/gcrm-enrichment-agent/
COPY agents/gcrm-scout-agent/      ./agents/gcrm-scout-agent/
COPY agents/gcrm-outreach-agent/   ./agents/gcrm-outreach-agent/
COPY agents/gcrm-followup-agent/   ./agents/gcrm-followup-agent/
COPY agents/gcrm-opportunity-agent/ ./agents/gcrm-opportunity-agent/
COPY gcrm/                         ./gcrm/
COPY scripts/                      ./scripts/
COPY pyproject.toml uv.lock ./

RUN uv sync --locked --extra agents --no-dev --no-editable

FROM python:3.13-alpine@sha256:1e1f6334529d1fb26a2ef619d7cffb30a7c7d7cc1cc7338ebee283a58d1aeaca AS runtime
WORKDIR /app

# Build tools, resolver caches and vendored package-manager libraries stay out
# of the running service. Python's pip bootstrap archive is not needed either.
RUN /usr/local/bin/python -m pip uninstall --yes pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && rm -f /sbin/apk \
    && addgroup -g 10001 engcrm \
    && adduser -u 10001 -G engcrm -h /app -H -D -s /sbin/nologin engcrm \
    && mkdir -p /data/card-images \
    && chown 10001:10001 /data/card-images

COPY --from=builder /app/.venv /app/.venv
COPY gcrm/ ./gcrm/
COPY scripts/ ./scripts/
COPY infra/ ./infra/
COPY docker-compose.yml ./infra/docker-compose.yml

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 XDG_CACHE_HOME=/tmp/cache
USER 10001:10001

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "gcrm.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
