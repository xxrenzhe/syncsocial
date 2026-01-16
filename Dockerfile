FROM node:20-bookworm-slim AS web_builder

WORKDIR /src/apps/web

ARG NEXT_PUBLIC_API_BASE_URL=/api
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NEXT_DISABLE_TURBOPACK=1

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./
RUN npm run build

# Prepare Next standalone runtime
RUN cp -r .next/static .next/standalone/.next/static \
  && cp -r public .next/standalone/public


FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    nginx supervisor ca-certificates \
    xvfb fluxbox x11vnc novnc websockify \
  && rm -rf /var/lib/apt/lists/*

# Install Node.js (runtime for Next standalone)
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl gnupg \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# Copy API + Browser Node sources (keep separate to avoid Python package name conflicts)
COPY apps/api /opt/apps/api
COPY apps/browser-node /opt/apps/browser-node

# Create isolated virtualenvs for api vs browser-node (dependency isolation)
RUN python -m venv /opt/venv-api \
  && /opt/venv-api/bin/pip install --no-cache-dir -r /opt/apps/api/requirements.txt

RUN python -m venv /opt/venv-browser-node \
  && /opt/venv-browser-node/bin/pip install --no-cache-dir -r /opt/apps/browser-node/requirements.txt

# Copy web standalone runtime
COPY --from=web_builder /src/apps/web/.next/standalone /opt/apps/web
COPY --from=web_builder /src/apps/web/.next/static /opt/apps/web/.next/static
COPY --from=web_builder /src/apps/web/public /opt/apps/web/public

# Nginx + Supervisor configs
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/supervisord.conf /etc/supervisor/supervisord.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Defaults for single-container internal routing
ENV BROWSER_CLUSTER_MODE=remote
ENV BROWSER_NODE_API_BASE_URL=http://127.0.0.1:9300
ENV NOVNC_PUBLIC_URL=/vnc/vnc.html?autoconnect=1&resize=remote
ENV BROWSER_NODE_HEADLESS=false
ENV CORS_ORIGINS=http://localhost

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]

