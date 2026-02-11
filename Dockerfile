# Build stage
FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder

# Install git and g++
RUN apt-get update && apt-get install -y git g++

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_INSTALL_DIR=/python
ENV UV_PYTHON_PREFERENCE=only-managed

RUN uv python install 3.13

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY pyproject.toml uv.lock /app/
COPY immersive_library/ /app/immersive_library/
COPY static/ /app/static/
COPY templates/ /app/templates/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-groups --no-group dev

# Install Playwright Chromium for headless rendering
RUN --mount=type=cache,target=/root/.cache/ms-playwright \
    /app/.venv/bin/playwright install --with-deps chromium

# Final stage
FROM debian:bookworm-slim

# Create a non-root user
RUN groupadd -r app && useradd -r -g app app

# Copy Python runtime and app
COPY --from=builder --chown=app:app /python /python
COPY --from=builder --chown=app:app /app /app

# Environment
ENV PATH="/app/.venv/bin:$PATH"
ENV FASTAPI_WORKERS=2
ENV REDIS_HOST="redis"
ENV DATABASE_URL="sqlite:////data/database.db"
WORKDIR /app

# Switch to non-root user
USER app

# Run FastAPI with configurable workers
CMD fastapi run --host 0.0.0.0 --workers $FASTAPI_WORKERS /app/immersive_library/main.py