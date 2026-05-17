#!/bin/bash
set -e

# Build sync DSN for alembic from environment variables
export ALEMBIC_DB_URL="postgresql://${POSTGRES_USER:-yanheng}:${POSTGRES_PASSWORD:-123456}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-rag_system}"

echo "Running database migrations..."
alembic upgrade head

echo "Starting RAG system..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
