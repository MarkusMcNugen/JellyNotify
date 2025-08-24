# Multi-stage Dockerfile for Jellynouncer with Web Interface
# Optimized for security, size, and build caching

# ============================================
# Stage 1: Frontend Builder
# ============================================
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Copy package files for dependency caching
COPY web/package*.json ./

# Install dependencies using ci for reproducible builds
# npm ci is preferred over npm install when package-lock.json exists
RUN npm ci --omit=dev

# Copy frontend source code
COPY web/ ./

# Build the production bundle
RUN npm install

# ============================================
# Stage 2: Python Base 
# ============================================
FROM python:3.13-slim AS python-base

# Install system dependencies and security updates
RUN apt-get update && apt-get install -y \
    curl \
    sqlite3 \
    jq \
    gosu \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/*

# Create non-root user for security
RUN groupadd -r jellynouncer -g 1000 && \
    useradd -r -g jellynouncer -u 1000 -m -s /bin/bash jellynouncer

# Set working directory
WORKDIR /app

# Copy and install Python requirements (cached layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# ============================================
# Stage 3: Production Image
# ============================================
FROM python-base AS production

# Copy application code with proper ownership
COPY --chown=jellynouncer:jellynouncer main.py ./
COPY --chown=jellynouncer:jellynouncer jellynouncer/ ./jellynouncer/
COPY --chown=jellynouncer:jellynouncer docker-entrypoint.sh /usr/local/bin/

# Copy default templates and config
COPY --chown=jellynouncer:jellynouncer templates/ /app/defaults/templates/
COPY --chown=jellynouncer:jellynouncer config/ /app/defaults/config/

# Copy built frontend from builder stage
COPY --from=frontend-builder --chown=jellynouncer:jellynouncer /build/dist /app/web/dist

# Create necessary directories with proper permissions
RUN mkdir -p \
    /app/data \
    /app/data/certificates \
    /app/logs \
    /app/config \
    /app/templates \
    /app/web/dist \
    && chown -R jellynouncer:jellynouncer /app \
    && chmod -R 755 /app \
    && chmod 700 /app/data/certificates \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /app/main.py

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=1984 \
    WEB_PORT=1985 \
    TERM=xterm-256color \
    LOG_LEVEL=INFO \
    JELLYNOUNCER_RUN_MODE=all \
    PATH="/app:${PATH}"

# Expose ports
# 1984: Webhook service
# 1985: Web interface (HTTP)
# 9000: Web interface (HTTPS when SSL is configured)
EXPOSE 1984 1985 9000

# Volume mounts for persistent data
VOLUME ["/app/config", "/app/data", "/app/logs", "/app/templates"]

# Health check for both services
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT:-1984}/health && \
        curl -f http://localhost:${WEB_PORT:-1985}/api/health || exit 1

# Set the entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command runs both services
CMD ["python", "/app/main.py"]