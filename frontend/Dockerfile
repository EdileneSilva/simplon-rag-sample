# syntax=docker/dockerfile:1.7

# --- Base stage: Bun on Debian slim ---
FROM oven/bun:1-debian AS base

ENV NODE_ENV=development

WORKDIR /app

COPY package.json bun.lock ./

# --- Dev stage: full deps, Vite dev server with HMR ---
FROM base AS dev

RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

COPY . .

EXPOSE 5173
CMD ["bun", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# --- Build stage: produce static SPA into /app/build ---
FROM base AS build

ARG PUBLIC_API_URL=http://localhost:8000
ENV PUBLIC_API_URL=${PUBLIC_API_URL} \
    NODE_ENV=production

RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

COPY . .

RUN bun run build

# --- Prod stage: nginx serving the prerendered static SPA ---
FROM nginx:1.27-alpine AS prod

COPY --from=build /app/build /usr/share/nginx/html

RUN <<'EOF' cat > /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

EXPOSE 80