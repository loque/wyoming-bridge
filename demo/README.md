# Wyoming Bridge Demo

## Components

- **target**: Simple Wyoming target emulator.
- **logger**: Simple processor that logs all events it receives.
- **coordinator**: HTTP API to send Wyoming events to the bridge.

## Usage

1. Build and start the stack:

```bash
docker compose up --build
```

2. Send an event to the bridge:

```bash
curl -X POST http://localhost:8080/event -H "Content-Type: application/json" -d '{"type": "audio-start", "data": {"rate": 16000, "width": 2, "channels": 1}}'
```

3. Check the logger output in the logs.
