# Wyoming Bridge Ping Pong Demo

This demo showcases the Wyoming Bridge's ability to forward events to observer
and enricher processors. It demonstrates how an observer processor—here, a
simple logger—can receive and log all Wyoming events passing through the bridge,
without affecting the event flow. It also demonstrates how an enricher
processor—here, a simple speaker ID processor—can enrich the event data before
it is sent back to the source. This setup helps verify that both processors are
correctly integrated and functioning as intended.

## Services

- **coordinator**: HTTP API to send Wyoming events to the bridge.
- **wyoming-bridge**: The Wyoming bridge that connects the coordinator to the target.
- **logger**: Simple observer processor that logs all events it receives.
- **speaker_id**: Simple enricher processor that adds speaker ID information to the Detection event.
- **target**: Simple Wyoming target emulator, will echo events back to the source.

## Usage

### 1. Start the stack:

```bash
docker compose up
```

### 2. Send an AudioStart event to the bridge through the coordinator's API:

```bash
curl -X POST http://localhost:8080/event -H "Content-Type: application/json" -d '{"type": "audio-start", "data": {"rate": 16000, "width": 2, "channels": 1}}'
```

You should see logs similar to:

```bash
wyoming-bridge-demo       | DEBUG  conns   Event handler connected to source: 46007404319262
wyoming-bridge-demo       | DEBUG  conns   Sending event down to target: audio-start
wyoming-coordinator-demo  | 172.27.0.1 - - [06/Jun/2025 16:55:17] "POST /event HTTP/1.1" 201 -
wyoming-target-demo       | INFO:target.handler:Returning event [audio-start]: {'rate': 16000, 'width': 2, 'channels': 1}
wyoming-logger-demo       | INFO:logger.handler:Logging event [audio-start]: {'rate': 16000, 'width': 2, 'channels': 1}
wyoming-bridge-demo       | DEBUG  conns   Sending event down to processor_logger: audio-start
wyoming-bridge-demo       | DEBUG  conns   Received event from target: audio-start
wyoming-bridge-demo       | DEBUG  conns   Sending event up to source: audio-start

```

### 3. Send a Detection event to the bridge through the coordinator's API:

```bash
curl -X POST http://localhost:8080/event -H "Content-Type: application/json" -d '{"type": "detection", "data": {"name": "ok_nabu", "timestamp": "2025-06-06T16:55:17.123456Z"}}'
```

You should see logs similar to:

```bash
wyoming-bridge-demo       | DEBUG  conns   Sending event down to target: detection
wyoming-target-demo       | INFO:target.handler:Returning event [detection]: {'name': 'ok_nabu', 'timestamp': '2025-06-06T16:55:17.123456Z'}
wyoming-coordinator-demo  | 172.27.0.1 - - [06/Jun/2025 21:02:52] "POST /event HTTP/1.1" 201 -
wyoming-bridge-demo       | DEBUG  conns   Received event from target: detection. Data: {'name': 'ok_nabu', 'timestamp': '2025-06-06T16:55:17.123456Z'}
wbdemo-pp-speakerid       | INFO:speaker_id.handler:Logging event [detection]: {'name': 'ok_nabu', 'timestamp': '2025-06-06T16:55:17.123456Z', 'correlation_id': 'b910b75d-fc3b-421b-a82a-e71d0bbea18b_speaker_id'}
wyoming-bridge-demo       | DEBUG  conns   Sending event down to processor_speaker_id: detection
wbdemo-pp-speakerid       | INFO:speaker_id.handler:detection correlation_id: b910b75d-fc3b-421b-a82a-e71d0bbea18b_speaker_id
# Notice the added speaker_id in the event data
wyoming-bridge-demo       | DEBUG  conns   Received event from processor_speaker_id: detection. Data: {'name': 'ok_nabu', 'timestamp': '2025-06-06T16:55:17.123456Z', 'correlation_id': 'b910b75d-fc3b-421b-a82a-e71d0bbea18b_speaker_id', 'speaker_id': 'static-speaker-1'}
```
