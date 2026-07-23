# DataHub Reflex — Production Dockerfile
# Multi-stage build for minimal image size
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY reflex/ reflex/
COPY ui/ ui/
COPY templates/ templates/
COPY static/ static/
COPY scripts/ scripts/
COPY datasets/ datasets/

RUN pip install --no-cache-dir -e ".[dev]"

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY reflex/ reflex/
COPY ui/ ui/
COPY templates/ templates/
COPY static/ static/
COPY scripts/ scripts/
COPY datasets/ datasets/
COPY .env.example .env.example
COPY LICENSE README.md ./

# Create non-root user
RUN useradd --create-home --shell /bin/bash reflex \
    && mkdir -p /app/data \
    && chown -R reflex:reflex /app
USER reflex

# Health check uses the built-in API endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/health')" || exit 1

EXPOSE 5000

ENV REFLEX_UI_PORT=5000
ENV REFLEX_UI_HOST=0.0.0.0
ENV REFLEX_DB_PATH=/app/data/reflex.db
ENV REFLEX_LESSONS_DIR=/app/data
ENV REFLEX_LLM_MODE=deterministic
ENV REFLEX_UI_AUTH_REQUIRED=true

# The workflow runner is intentionally process-local and SQLite is the
# persistence backend for the MVP. Keep one worker process and use threads so
# startup cannot race on WAL initialization or split the active run state.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "ui.app:app"]
