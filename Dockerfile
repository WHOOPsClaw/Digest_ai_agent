FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/newsbrief/newsbrief"
LABEL org.opencontainers.image.description="Self-hosted AI news digest for Telegram"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# System deps for matplotlib + psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY newsbrief/ ./newsbrief/
COPY data/ ./data/

RUN pip install --no-cache-dir -e .

# Non-root user
RUN useradd -m newsbrief && chown -R newsbrief:newsbrief /app
USER newsbrief

# Volumes: config, state, plugins
VOLUME ["/app/data", "/app/config.yaml"]

HEALTHCHECK --interval=5m --timeout=30s --start-period=30s \
  CMD python -c "import newsbrief" || exit 1

# Default entrypoint
ENTRYPOINT ["newsbrief"]
CMD ["daemon"]
