# Wyoming Bridge Docker

This directory contains the Dockerfile and related files for containerizing the Wyoming Bridge service.

## Building the Image

From this directory (`wyoming_bridge/`), run:

```bash
docker build -t wyoming-bridge .
```

## Running the Container

The Wyoming Bridge requires a connection to a Wyoming service. You must provide the `--target-uri` parameter:

```bash
# Basic usage
docker run -p 5004:5004 wyoming-bridge --target-uri tcp://your-wyoming-service:10400

# With debug logging
docker run -p 5004:5004 wyoming-bridge --target-uri tcp://your-wyoming-service:10400 --debug

# Custom bridge URI
docker run -p 8080:8080 wyoming-bridge --uri tcp://0.0.0.0:8080 --target-uri tcp://your-wyoming-service:10400
```

## Docker Compose Example

```yaml
version: "3.8"
services:
  wyoming-bridge:
    build: .
    ports:
      - "5004:5004"
    command:
      [
        "python",
        "-m",
        "wyoming_bridge",
        "--uri",
        "tcp://0.0.0.0:5004",
        "--target-uri",
        "tcp://wyoming-service:10400",
      ]
    depends_on:
      - wyoming-service

  # Your Wyoming service
  wyoming-service:
    # ... wyoming service configuration
```

## Environment Variables

The container doesn't use environment variables by default, but you can modify the CMD or use docker run arguments to pass configuration.

## Security

- The container runs as a non-root user (`app`)
- Only necessary files are copied (see `.dockerignore`)
- Uses Python 3.12 slim image for smaller attack surface
