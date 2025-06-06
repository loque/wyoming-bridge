# Wyoming Bridge Ping Pong Demo

## Services

- **coordinator**: HTTP API to send Wyoming events to the bridge.
- **wyoming-bridge**: The Wyoming bridge that connects the coordinator to the target.
- **logger**: Simple observer processor that logs all events it receives.
- **target**: Simple Wyoming target emulator, will echo events back to the source.

## Usage

1. Start the stack:

```bash
docker compose up
```

2. Send an event to the bridge through the coordinator's API:

```bash
curl -X POST http://localhost:8080/event -H "Content-Type: application/json" -d '{"type": "audio-start", "data": {"rate": 16000, "width": 2, "channels": 1}}'
```

3. Check the logger output in the logs.
