# Mock Playback Service

A mock Wyoming playback service that collects audio chunks and saves them as timestamped WAV files instead of playing them through speakers.

## Features

- Handles Wyoming protocol audio events (AudioStart, AudioChunk, AudioStop)
- Collects audio chunks during playback sessions
- Saves audio as timestamped WAV files in the `output/` directory
- Sends proper `Played` events back to clients
- Supports various audio formats and sample rates

## Usage

Run the mock playback service:

```bash
python -m playback --uri tcp://0.0.0.0:10601
```

## Output

Audio files are saved in the `output/` directory with filenames in the format:
```
audio_YYYYMMDD_HHMMSS_mmm.wav
```

Where:
- `YYYYMMDD` is the date
- `HHMMSS` is the time
- `mmm` is milliseconds

## Docker

The service can be used as a drop-in replacement for real playback services in Docker Compose configurations.
