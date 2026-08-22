# syntax=docker.io/docker/dockerfile:1

FROM node:22-alpine AS base

# Install pnpm
RUN corepack enable && corepack prepare pnpm@10.11.0 --activate

# Install dependencies only when needed
FROM base AS deps
WORKDIR /app

# Install dependencies based on the preferred package manager
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY patches ./patches
COPY prisma ./prisma
RUN pnpm install --frozen-lockfile
RUN pnpm run prisma-generate-client

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/src/generated ./src/generated
COPY . .

# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_OPTIONS="--max-old-space-size=1536"

ARG APP_VERSION=0.0.0
ENV APP_VERSION=${APP_VERSION}

RUN pnpm build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Expose global.gc so the scan loop can force GC of off-heap cover-art buffers
# between batches, preventing the external-memory SIGSEGV on large libraries (#22).
ENV NODE_OPTIONS="--expose-gc"

# Runtime dependencies
RUN apk add --no-cache su-exec sqlite shadow ffmpeg

# Create data and music directories (ownership set at runtime by entrypoint)
RUN mkdir -p /data /music

COPY --from=builder /app/public ./public

# Automatically leverage output traces to reduce image size
# https://nextjs.org/docs/advanced-features/output-file-tracing
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# libsql loads its native binding with a dynamic require. Next.js standalone
# tracing can omit that optional platform package, so copy the package that
# pnpm actually installed for this Alpine build from the builder stage.
RUN --mount=type=bind,from=builder,source=/app/node_modules,target=/mnt/builder-node-modules,ro set -eux; native_src="$(find /mnt/builder-node-modules/.pnpm -type d -path '*/node_modules/@libsql/linux-*musl*' | head -n 1)"; test -n "${native_src}"; native_name="$(basename "${native_src}")"; mkdir -p /app/node_modules/@libsql; cp -a "${native_src}" "/app/node_modules/@libsql/${native_name}"; libsql_entry="$(find /app/node_modules -type f -path '*/libsql/index.js' | head -n 1)"; test -n "${libsql_entry}"; node -e "require(process.argv[1]); console.log('libsql native runtime OK')" "${libsql_entry}"

# Prisma: copy schema + config, install CLI for db push & studio at runtime
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/prisma.config.ts ./prisma.config.ts
RUN npm install -g prisma@7.4.0 dotenv@17.3.1 && \
    mkdir -p node_modules && \
    ln -s /usr/local/lib/node_modules/prisma node_modules/prisma && \
    ln -s /usr/local/lib/node_modules/dotenv node_modules/dotenv

# Entrypoint script
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["./docker-entrypoint.sh"]
