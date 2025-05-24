# Wyoming Wake Bridge Docker

This directory contains the Dockerfile and related files for containerizing the Wyoming Wake Bridge service.

## Building the Image

From this directory (`wake_bridge/`), run:

```bash
docker build -t wyoming-wake-bridge .
```

## Running the Container

The wake bridge requires a connection to a Wyoming wake word detection service. You must provide the `--wake-uri` parameter:

```bash
# Basic usage
docker run -p 5004:5004 wyoming-wake-bridge --wake-uri tcp://your-wake-service:10400

# With debug logging
docker run -p 5004:5004 wyoming-wake-bridge --wake-uri tcp://your-wake-service:10400 --debug

# Custom bridge URI
docker run -p 8080:8080 wyoming-wake-bridge --uri tcp://0.0.0.0:8080 --wake-uri tcp://your-wake-service:10400
```

## Docker Compose Example

```yaml
version: '3.8'
services:
  wake-bridge:
    build: .
    ports:
      - "5004:5004"
    command: ["python", "-m", "wake_bridge", "--uri", "tcp://0.0.0.0:5004", "--wake-uri", "tcp://wake-service:10400"]
    depends_on:
      - wake-service
  
  # Your wake word detection service
  wake-service:
    # ... wake service configuration
```

## Environment Variables

The container doesn't use environment variables by default, but you can modify the CMD or use docker run arguments to pass configuration.

## Security

- The container runs as a non-root user (`app`)
- Only necessary files are copied (see `.dockerignore`)
- Uses Python 3.12 slim image for smaller attack surface
