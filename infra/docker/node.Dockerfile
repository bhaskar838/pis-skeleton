# Next.js apps (web, admin) built in standalone mode. Usage: --build-arg APP=web|admin

FROM node:22-alpine AS base
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml* .npmrc* ./
COPY apps/web/package.json apps/web/package.json
COPY apps/admin/package.json apps/admin/package.json
COPY packages/ts/ui/package.json packages/ts/ui/package.json
COPY packages/ts/api-client/package.json packages/ts/api-client/package.json
COPY packages/ts/config/package.json packages/ts/config/package.json
COPY packages/ts/auth/package.json packages/ts/auth/package.json
COPY tests/e2e/package.json tests/e2e/package.json
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile

FROM deps AS build
ARG APP=web
# Baked into the security headers (CSP connect-src / form-action) at build time; override per environment.
ARG AUTH_KEYCLOAK_ISSUER=http://keycloak.localhost:8080/realms/dcs
ARG NEXT_PUBLIC_REALTIME_URL=ws://localhost:8003/v1/events
ENV AUTH_KEYCLOAK_ISSUER=${AUTH_KEYCLOAK_ISSUER} NEXT_PUBLIC_REALTIME_URL=${NEXT_PUBLIC_REALTIME_URL}
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter "@dcs/${APP}" build

FROM node:22-alpine AS runtime
ARG APP=web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S dcs && adduser -S dcs -G dcs
COPY --from=build --chown=dcs:dcs /repo/apps/${APP}/.next/standalone ./
COPY --from=build --chown=dcs:dcs /repo/apps/${APP}/.next/static ./apps/${APP}/.next/static
COPY --from=build --chown=dcs:dcs /repo/apps/${APP}/public ./apps/${APP}/public
USER dcs
ENV APP_DIR=apps/${APP}
EXPOSE 3000
CMD ["sh", "-c", "node ${APP_DIR}/server.js"]
