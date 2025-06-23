import asyncio
import logging
import time
import wave

from wyoming.audio import AudioChunk, AudioStart

_LOGGER = logging.getLogger(__name__)

class StreamingServer:
    def __init__(self, file_queue: asyncio.Queue, event_writer) -> None:
        self._file_queue = file_queue
        self._event_writer = event_writer

        # Audio configuration
        self.samples_per_chunk = 1024
        self.sample_rate = 16000
        self.sample_width = 2
        self.channels = 1

        # Start the continuous audio streaming task
        self._task = asyncio.create_task(self._continuous_audio_stream())

    async def stop(self) -> bool:
        success = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for streaming task to cancel")
                success = False
            self._task = None
        return success

    async def _continuous_audio_stream(self) -> None:
        try:
            # Send initial AudioStart
            await self._event_writer(AudioStart(
                rate=self.sample_rate,
                width=self.sample_width,
                channels=self.channels,
                timestamp=time.monotonic_ns()
            ).event())

            _LOGGER.info("Started continuous audio streaming")

            while True:
                # Check if there's a new file to stream
                try:
                    filepath = self._file_queue.get_nowait()
                    _LOGGER.info("Trigger audio file streaming: %s", filepath)
                    await self._stream_file_chunks(filepath)

                    # Stream ~0.5s of silence after the file to ensure a clean break.
                    for _ in range(8):
                        await self._stream_silence_chunk()
                except asyncio.QueueEmpty:
                    # Stream silence
                    await self._stream_silence_chunk()

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            _LOGGER.debug("Continuous audio stream cancelled")
        except Exception:
            _LOGGER.exception("Error in continuous audio stream")

    async def _stream_file_chunks(self, filepath: str) -> None:
        """Stream chunks from a WAV file."""
        try:
            with wave.open(str(filepath), "rb") as wav_file:
                while True:
                    audio_bytes = wav_file.readframes(self.samples_per_chunk)
                    if not audio_bytes:
                        break  # End of file

                    chunk = AudioChunk(
                        rate=self.sample_rate,
                        width=self.sample_width,
                        channels=self.channels,
                        audio=audio_bytes,
                        timestamp=time.monotonic_ns(),
                    )
                    await self._event_writer(chunk.event())

                    # Wait for real-time playback
                    await asyncio.sleep(chunk.seconds)

        except Exception as e:
            _LOGGER.error("Error streaming file %s: %s", filepath, e)

    async def _stream_silence_chunk(self) -> None:
        """Stream a chunk of silence."""
        # Generate silence (zeros)
        silence_bytes = bytes(self.samples_per_chunk * self.sample_width * self.channels)

        chunk = AudioChunk(
            rate=self.sample_rate,
            width=self.sample_width,
            channels=self.channels,
            audio=silence_bytes,
            timestamp=time.monotonic_ns(),
        )
        await self._event_writer(chunk.event())

        # Wait for real-time duration
        chunk_duration = self.samples_per_chunk / self.sample_rate
        await asyncio.sleep(chunk_duration)