# Wyoming Bridge Ping Pong Demo

This demo showcases the Wyoming Bridge's ability to forward events to observer
processors. It demonstrates how an observer processor—here, a simple logger—can
receive and log all Wyoming events passing through the bridge, without affecting
the event flow. This setup helps verify that observer processors are correctly
integrated and functioning as intended.

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

You should see logs similar to:

```
wyoming-bridge-demo       | DEBUG  conns   Event handler connected to source: 46007404319262
wyoming-bridge-demo       | DEBUG  conns   Sending event down to target: audio-start
wyoming-coordinator-demo  | 172.27.0.1 - - [06/Jun/2025 16:55:17] "POST /event HTTP/1.1" 201 -
wyoming-target-demo       | INFO:target.handler:Returning event [audio-start]: {'rate': 16000, 'width': 2, 'channels': 1}
wyoming-logger-demo       | INFO:logger.handler:Logging event [audio-start]: {'rate': 16000, 'width': 2, 'channels': 1}
wyoming-bridge-demo       | DEBUG  conns   Sending event down to processor_logger: audio-start
wyoming-bridge-demo       | DEBUG  conns   Received event from target: audio-start
wyoming-bridge-demo       | DEBUG  conns   Sending event up to source: audio-start

```
