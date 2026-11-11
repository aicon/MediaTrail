# --- Builder stage: build the virtualenv with uv ---
FROM ghcr.io/astral-sh/uv:python3.12-alpine3.23 AS builder

# Disable development dependencies
ENV UV_NO_DEV=1
# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy from cache instead of symlinking (cache is discarded with the builder)
ENV UV_LINK_MODE=copy

WORKDIR /mediatrail

COPY ./pyproject.toml ./pyproject.toml
COPY ./uv.lock ./uv.lock

# The preview API imports rest_framework and drf_spectacular, but this
# branch's lockfile does not list them. Install them after the locked sync
# so the docs-group git dependency is not resolved again.
RUN uv sync --locked \
    && uv pip install --python /mediatrail/.venv/bin/python \
        "djangorestframework~=3.16.1" \
        "drf-spectacular~=0.28.0"

# --- Final stage: minimal runtime image ---
FROM python:3.12-alpine3.23

# https://stackoverflow.com/questions/58701233/docker-logs-erroneously-appears-empty-until-container-stops
ENV PYTHONUNBUFFERED=1

# Version label only. API keys, including a Gemini key, are runtime settings.
# Do not pass them as build arguments and do not copy them into this image.
ARG VERSION=0.25.22
# Set it as an environment variable
ENV VERSION=$VERSION
# Put the virtualenv on PATH so python/gunicorn/celery/supervisord resolve directly
ENV PATH="/mediatrail/.venv/bin:$PATH"
# Redis runs inside this image. Override only to point at an external Redis.
ENV REDIS_URL=redis://127.0.0.1:6379

WORKDIR /mediatrail

COPY ./entrypoint.sh /entrypoint.sh
COPY ./supervisord.conf /etc/supervisord.conf
COPY ./nginx.conf /etc/nginx/nginx.conf
# Generate a copy of the nginx config with IPv6 support.
RUN sed 's/listen 8000;/listen 8000; listen [::]:8000;/' /etc/nginx/nginx.conf > /etc/nginx/nginx.ipv6.conf

RUN apk add --no-cache nginx redis shadow \
    && chmod +x /entrypoint.sh \
    # create user abc for later PUID/PGID mapping
    && useradd -U -M -s /bin/sh abc \
    # Create required nginx directories and set permissions
    && mkdir -p /var/log/nginx \
    && mkdir -p /var/lib/nginx/body

# Copy the pre-built virtualenv from the builder stage
COPY --from=builder /mediatrail/.venv /mediatrail/.venv

# Django app
COPY src ./
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["/entrypoint.sh"]

HEALTHCHECK --interval=45s --timeout=15s --start-period=30s --retries=5 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8000/health/ || exit 1
