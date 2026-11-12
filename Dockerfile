# Stage 1: Build modern War Room dashboard frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci --prefer-offline || npm install
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
# Copy prebuilt frontend assets into FastAPI static directory
COPY --from=frontend-builder /app/web/dist /app/aegis_os/static

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
