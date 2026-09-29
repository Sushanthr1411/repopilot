FROM python:3.11-slim

WORKDIR /app

# Build deps for native packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ curl git && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (pip, not uv, for maximum portability)
# uv's no-binary-package override is Windows-specific — not needed on Linux.
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.30.0" \
        "pydantic>=2.7.0" \
        "pydantic-settings[dotenv]>=2.3.0" \
        "sqlalchemy[asyncio]>=2.0.0" \
        "asyncpg>=0.29.0" \
        "alembic>=1.13.0" \
        "networkx>=3.0" \
        "chromadb>=0.4.0" \
        "sentence-transformers>=2.7.0" \
        "litellm>=1.103.0" \
        "python-dotenv>=1.0.0"

# Copy application code
COPY app/      ./app/
COPY alembic/  ./alembic/
COPY alembic.ini ./

# Runtime data directories
RUN mkdir -p /app/data/chroma /repos

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
