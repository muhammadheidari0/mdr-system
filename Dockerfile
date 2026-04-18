FROM node:20-alpine AS frontend_builder

WORKDIR /src

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=180

ARG APP_UID=1000
ARG APP_GID=1000

WORKDIR /app

COPY requirements.txt .
RUN set -eux; \
    apt_opts='-o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30'; \
    find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) -exec sed -i 's|http://deb.debian.org|https://deb.debian.org|g; s|http://security.debian.org|https://security.debian.org|g' {} +; \
    apt-get ${apt_opts} update; \
    apt-get ${apt_opts} install -y --no-install-recommends --fix-missing gcc libpq-dev libmagic1 file; \
    rm -rf /var/lib/apt/lists/*
RUN groupadd --gid "${APP_GID}" mdr \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin mdr
RUN pip install --no-cache-dir --retries 10 --timeout 180 -r requirements.txt

COPY . .
RUN rm -rf /app/static/dist
COPY --from=frontend_builder /src/static/dist /app/static/dist
RUN chmod +x /app/docker/start.sh /app/docker/start_worker.sh \
    && if [ ! -f /app/data_sources/master_data.xlsx ]; then echo "ERROR: required seed file missing: /app/data_sources/master_data.xlsx"; exit 1; fi
RUN mkdir -p /app/database /app/data_store /app/archive_storage /app/logs \
    && chown -R mdr:mdr /app /home/mdr

USER mdr

EXPOSE 8000

CMD ["/app/docker/start.sh"]
