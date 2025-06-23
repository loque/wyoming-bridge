FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements for better layer caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . wyoming_bridge/

# Create non-root user for security
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 5004

# Required: --target-uri must be provided when running
CMD ["python", "-m", "wyoming_bridge", "--uri", "tcp://0.0.0.0:5004"]