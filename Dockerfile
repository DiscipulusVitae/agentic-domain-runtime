# Official uv image with Python 3.13.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Working directory inside the reviewer image.
WORKDIR /app

# Keep container execution non-interactive and deterministic.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy dependency metadata first for better layer caching.
COPY pyproject.toml uv.lock ./

# Install dependencies without installing the project package yet.
RUN uv sync --frozen --no-install-project

# Copy public source, docs, local Supabase package, and safe defaults.
COPY src/ ./src/
COPY tests/ ./tests/
COPY docs/ ./docs/
COPY supabase/ ./supabase/
COPY README.md .env.example .gitignore ./

# Use the public-safe environment template so no secrets are required.
RUN cp .env.example .env

# Install the project package.
RUN uv sync --frozen

# Default to an interactive shell for manual reviewer exploration.
CMD ["/bin/bash"]
