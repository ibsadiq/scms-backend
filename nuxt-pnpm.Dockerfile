# ============================================
# Nuxt 3 Frontend Dockerfile (PNPM Version)
# Production-ready multi-stage build
# ============================================
#
# Copy this content to your Nuxt project as "Dockerfile"
# Location: ../ssync-frontend/Dockerfile

# ====================
# Base Stage
# ====================
FROM node:20-alpine AS base

# Install pnpm
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@latest --activate

# Install build dependencies
RUN apk add --no-cache libc6-compat

WORKDIR /app

# ====================
# Dependencies Stage
# ====================
FROM base AS deps

# Copy package files
COPY package.json pnpm-lock.yaml* ./

# Install dependencies
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

# ====================
# Development Stage
# ====================
FROM base AS development

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy project files
COPY . .

# Expose port
EXPOSE 3000

# Environment variables
ENV NUXT_HOST=0.0.0.0
ENV NUXT_PORT=3000
ENV NODE_ENV=development

# Development command with hot reload
CMD ["pnpm", "run", "dev", "--host", "0.0.0.0"]

# ====================
# Builder Stage
# ====================
FROM base AS builder

WORKDIR /app

# Copy dependencies
COPY --from=deps /app/node_modules ./node_modules

# Copy project files
COPY . .

# Build arguments for environment variables
ARG NUXT_PUBLIC_API_URL
ARG NUXT_PUBLIC_API_BASE

# Set build-time environment variables
ENV NUXT_PUBLIC_API_URL=${NUXT_PUBLIC_API_URL}
ENV NUXT_PUBLIC_API_BASE=${NUXT_PUBLIC_API_BASE}
ENV NODE_ENV=production
# Increase Node.js memory limit for build (4GB)
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Generate Nuxt configuration and TypeScript files
RUN pnpm exec nuxt prepare || true

# Build the application
RUN pnpm run build

# ====================
# Production Stage
# ====================
FROM base AS production

WORKDIR /app

# Copy built application from builder
COPY --from=builder /app/.output ./.output

# Copy necessary files
COPY --from=builder /app/package.json ./

# Create non-root user for security
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nuxt -u 1001

# Change ownership
RUN chown -R nuxt:nodejs /app

# Switch to non-root user
USER nuxt

# Expose port
EXPOSE 3000

# Environment variables
ENV NUXT_HOST=0.0.0.0
ENV NUXT_PORT=3000
ENV NODE_ENV=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

# Production command
CMD ["node", ".output/server/index.mjs"]
