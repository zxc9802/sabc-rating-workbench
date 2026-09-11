FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY app ./app
COPY lib ./lib
COPY next.config.ts tsconfig.json ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY public ./public
COPY sabc ./sabc
COPY scripts/start_cloud.py ./scripts/start_cloud.py
ENV PATH="/opt/venv/bin:$PATH" NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 SABC_DB=/data/sabc.db SABC_REQUIRE_AUTH=1 PORT=8080 HOSTNAME=0.0.0.0
EXPOSE 8080
CMD ["python", "scripts/start_cloud.py"]
