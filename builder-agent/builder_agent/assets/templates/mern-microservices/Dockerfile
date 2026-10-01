# syntax=docker/dockerfile:1
#
# One image definition for every deployable package in this workspace - the gateway, and each
# service under packages/<name>. Which one a build produces is a build argument, not a second
# Dockerfile, so a new service (scaffold/service copied to packages/<name>) is deployable the
# moment it exists, with nothing here to edit. This file is built in the cloud (AWS CodeBuild,
# see the mern-microservices deployment skill) - it is source code, never run with a local
# `docker build`/`docker run` on a developer machine.
#
#   docker build --build-arg SERVICE=packages/gateway -t gateway .
#   docker build --build-arg SERVICE=packages/catalog -t catalog .

FROM node:20-slim AS base
WORKDIR /app

# Installing from the whole workspace (every package's manifest, including ones this particular
# image will never run) keeps this file single and correct under npm workspace hoisting; the
# alternative is a second Dockerfile per service, which drifts.
FROM base AS deps
COPY package.json package-lock.json* ./
COPY client/package.json client/package.json
COPY packages ./packages
RUN npm ci

FROM deps AS client-build
COPY client ./client
RUN npm run build --workspace client

FROM base AS runtime
ARG SERVICE=packages/gateway
ENV NODE_ENV=production
ENV SERVICE_ENTRY=${SERVICE}
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json ./package.json
COPY packages ./packages
COPY --from=client-build /app/client/dist ./client/dist
RUN useradd --system --no-create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 4000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:'+(process.env.PORT||process.env.SERVICE_PORT||4000)+'/health',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))"
CMD ["sh", "-c", "node ${SERVICE_ENTRY}/src/server.js"]
