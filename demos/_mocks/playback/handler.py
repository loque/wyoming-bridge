"""Mock Playback Handler"""
import asyncio
import logging
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.server import AsyncEventHandler
from wyoming.snd import Played

_LOGGER = logging.getLogger(__name__)


class EventHandler(AsyncEventHandler):
    """Event handler for mock playback service that saves audio to files."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        
        self.client_id = str(time.monotonic_ns())
        self._audio_chunks = []
        self._chunk_converter: Optional[AudioChunkConverter] = None
        self._current_session: Optional[dict] = None
        self._output_dir = Path(__file__).parent / "output"
        self._output_dir.mkdir(exist_ok=True)
        
        _LOGGER.debug("EventHandler initialized for client: %s", self.client_id)

    async def handle_event(self, event: Event) -> bool:
        """Handle incoming Wyoming events."""
        if AudioStart.is_type(event.type):
            await self._handle_audio_start(event)
        elif AudioChunk.is_type(event.type):
            await self._handle_audio_chunk(event)
        elif AudioStop.is_type(event.type):
            await self._handle_audio_stop(event)

        return True

    async def _handle_audio_start(self, event: Event) -> None:
        """Handle audio start event."""
        audio_start = AudioStart.from_event(event)
        _LOGGER.debug("Audio start: %s", audio_start)
        
        # Initialize new session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
        self._current_session = {
            "timestamp": timestamp,
            "rate": audio_start.rate,
            "width": audio_start.width,
            "channels": audio_start.channels,
            "filename": f"audio_{timestamp}.wav"
        }
        
        # Reset audio chunks and converter
        self._audio_chunks = []
        self._chunk_converter = AudioChunkConverter(
            rate=audio_start.rate,
            width=audio_start.width,
            channels=audio_start.channels,
        )
        
        _LOGGER.info("Started new audio session: %s", self._current_session["filename"])

    async def _handle_audio_chunk(self, event: Event) -> None:
        """Handle audio chunk event."""
        if self._current_session is None or self._chunk_converter is None:
            _LOGGER.warning("Received audio chunk without audio start")
            return
            
        chunk = AudioChunk.from_event(event)
        chunk = self._chunk_converter.convert(chunk)
        self._audio_chunks.append(chunk.audio)
        
        _LOGGER.debug("Collected audio chunk: %d bytes", len(chunk.audio))

    async def _handle_audio_stop(self, event: Event) -> None:
        """Handle audio stop event and save audio to file."""
        if self._current_session is None:
            _LOGGER.warning("Received audio stop without audio start")
            await self.write_event(Played().event())
            return
            
        # Save audio to file
        await self._save_audio_file()
        
        # Send played event
        await self.write_event(Played().event())
        
        # Reset session
        self._current_session = None
        self._audio_chunks = []
        self._chunk_converter = None

    async def _save_audio_file(self) -> None:
        """Save collected audio chunks to a WAV file."""
        if not self._current_session or not self._audio_chunks:
            _LOGGER.warning("No audio data to save")
            return
            
        filepath = self._output_dir / self._current_session["filename"]
        
        try:
            # Combine all audio chunks
            audio_data = b"".join(self._audio_chunks)
            
            # Write WAV file
            with wave.open(str(filepath), "wb") as wav_file:
                wav_file.setnchannels(self._current_session["channels"])
                wav_file.setsampwidth(self._current_session["width"])
                wav_file.setframerate(self._current_session["rate"])
                wav_file.writeframes(audio_data)
            
            _LOGGER.info("Saved audio file: %s (%d bytes)", filepath, len(audio_data))
            
        except Exception as e:
            _LOGGER.error("Failed to save audio file %s: %s", filepath, e)

    async def disconnect(self) -> None:
        """Handle client disconnect."""
        _LOGGER.debug("Client disconnected: %s", self.client_id)
        
        # Save any remaining audio if session is active
        if self._current_session is not None:
            _LOGGER.info("Saving audio on disconnect")
            await self._save_audio_file()
            
        # Clean up
        self._current_session = None
        self._audio_chunks = []
        self._chunk_converter = None