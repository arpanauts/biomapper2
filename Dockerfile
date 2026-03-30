# ---- builder: install dependencies ----
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached unless pyproject.toml/uv.lock change)
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and install the project itself
COPY src/ src/
COPY README.md ./
RUN uv sync --frozen --no-dev

# ---- dev: development image with dev deps and test tools ----
FROM python:3.12-slim AS dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy everything from builder, then layer dev deps on top
COPY --from=builder /app /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy remaining files needed for development (tests, scripts, data, examples)
COPY tests/ tests/
COPY scripts/ scripts/
COPY data/ data/
COPY examples/ examples/

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "biomapper2.api.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]

# ---- prod: minimal production image ----
FROM python:3.12-slim AS prod

WORKDIR /app

# Create non-root user
RUN groupadd --system biomapper && useradd --system --gid biomapper biomapper

# Copy the built venv and source from builder
COPY --from=builder /app /app

# Create directories the app may write to
RUN mkdir -p cache results && chown -R biomapper:biomapper /app

USER biomapper

EXPOSE 8001

CMD ["/app/.venv/bin/uvicorn", "biomapper2.api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
