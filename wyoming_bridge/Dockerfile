# Wyoming Bridge Docker Image
# 
# Build: docker build -t wyoming-bridge .
# Run: docker run -p 5004:5004 wyoming-bridge --target-uri tcp://wake-service:10400
#
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the wyoming_bridge module
COPY . wyoming_bridge/

# Create a non-root user for security
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose the default port (configurable via --uri)
EXPOSE 5004

# Set the default command to run the wyoming_bridge module
# Required: --target-uri must be provided when running the container
# Example: docker run wyoming-bridge --target-uri tcp://wake-service:10400
CMD ["python", "-m", "wyoming_bridge", "--uri", "tcp://0.0.0.0:5004"]