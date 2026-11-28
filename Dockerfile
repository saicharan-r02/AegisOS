# Stage 1: Build the PR Pilot web UI (React + Vite). Output lands in /app/aegis_os/static.
FROM node:22-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# Stage 2: Production Python API and runtime environment
FROM python:3.12-slim
WORKDIR /app

# Install security tools and VCS
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Copy the built UI into the directory FastAPI serves
COPY --from=frontend-builder /app/aegis_os/static /app/aegis_os/static

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV AEGIS_WORKSPACE=/workspace
VOLUME ["/workspace", "/app/.aegis"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/missions || exit 1

ENTRYPOINT ["aegis"]
CMD ["server", "--host", "0.0.0.0", "--port", "8000"]
