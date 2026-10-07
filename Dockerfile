FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies required for PyBoy (SDL2) and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libsdl2-2.0-0 \
    libsdl2-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and web assets
COPY src/ ./src/
COPY static/ ./static/

# Prepare directories for ROMs and persistent save files
RUN mkdir -p /app/roms /app/saves

# Environment configurations
ENV HOST=0.0.0.0
ENV PORT=8080
ENV ROM_DIR=/app/roms
ENV SAVES_DIR=/app/saves
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-m", "src.main"]
