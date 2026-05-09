# syntax=docker/dockerfile:1.7
# ----------------------------------------------------------------------------
# Stage 1 — build the React/Vite bundle.
# VITE_API_URL is empty so client.ts emits relative URLs ("/findings",
# "/projects", ...) which nginx proxies to the mcp service.
# ----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps off the lockfile first so cached layers survive source edits.
COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

# Empty string → BASE in client.ts becomes "" → fetch uses same-origin.
ENV VITE_API_URL=""
RUN npm run build

# ----------------------------------------------------------------------------
# Stage 2 — serve static + reverse-proxy backend on the same origin.
# ----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Strip the default site so our config is the only one.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/dashboard.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
