FROM node:20-alpine AS frontend_builder

WORKDIR /src

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev libmagic1 file \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN rm -rf /app/static/dist
COPY --from=frontend_builder /src/static/dist /app/static/dist
RUN chmod +x /app/docker/start.sh /app/docker/start_worker.sh
RUN test -f /app/data_sources/master_data.xlsx || (echo "ERROR: required seed file missing: /app/data_sources/master_data.xlsx" && exit 1)

EXPOSE 8000

CMD ["/app/docker/start.sh"]
