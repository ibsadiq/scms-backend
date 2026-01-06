# SSync - Django Backend Dockerfile
# Multi-stage build for optimized production image

# Stage 1: Base Python image with dependencies
FROM python:3.13-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    gettext \
    libpq-dev \
    gcc \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Development image
FROM base as development

# Install development dependencies
RUN pip install --no-cache-dir \
    ipython \
    django-debug-toolbar \
    django-extensions

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/media /app/logs

# Expose port
EXPOSE 8000

# Run development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Stage 3: Production image
FROM base as production

# Install production server
RUN pip install --no-cache-dir gunicorn==21.2.0

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/media /app/logs

# Collect static files (will be done in entrypoint, but directory must exist)
RUN chmod +x /app/docker-entrypoint.sh || true

# Create non-root user
RUN useradd -m -u 1000 ssync && \
    chown -R ssync:ssync /app

USER ssync

# Expose port
EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "school.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
