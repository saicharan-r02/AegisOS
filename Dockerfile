FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY aegis-dashboard/package*.json ./
RUN npm install
COPY aegis-dashboard/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install -e .

COPY --from=frontend-builder /app/frontend/dist /app/aegis_os/web/static

EXPOSE 8000

CMD ["aegis","server","--host","0.0.0.1","--port","8000"]
