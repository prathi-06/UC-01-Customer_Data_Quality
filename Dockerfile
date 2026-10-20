# Multi-stage Dockerfile for Customer Data Quality SaaS

# Stage 1: Build React + TypeScript frontend
FROM node:20-alpine AS build-web
WORKDIR /web
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# Stage 2: Python production runtime
FROM python:3.12-slim
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install runtime dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/
COPY seed.json .
COPY fixtures/ fixtures/

# Copy built frontend assets
COPY --from=build-web /web/dist web/dist

# Security: run as non-root user
RUN adduser --disabled-password --gecos "" --uid 10001 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
