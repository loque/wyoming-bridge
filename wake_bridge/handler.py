import asyncio
import logging

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.wake import Detect, NotDetected
from wyoming.info import Info, Describe
from wyoming.event import Event
from wyoming.client import AsyncClient
from wyoming.server import AsyncEventHandler

_LOGGER = logging.getLogger(__name__)


class WakeBridgeEventHandler(AsyncEventHandler):
    """Handle events from the Wake Bridge."""

    def __init__(
        self,
        wyoming_info: Info,
        wake_client: AsyncClient,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.wyoming_info_event = wyoming_info.event()
        self.wake_client = wake_client
        self._client_listener_task = asyncio.create_task(
            self._listen_to_client())
        self._closed = False

    async def shutdown(self):
        """Cancel the client listener task and wait for it to finish."""
        if self._closed:
            return
        self._closed = True
        if self._client_listener_task:
            self._client_listener_task.cancel()
            try:
                await self._client_listener_task
            except asyncio.CancelledError:
                pass

    async def _listen_to_client(self):
        """Listen for events from the Wyoming client and forward them to the wake service."""
        _LOGGER.debug("Listening for events from the Wyoming client")
        try:
            while True:
                event = await self.wake_client.read_event()
                if event is None:
                    break  # Client disconnected

                if Detect.is_type(event.type):
                    detect = Detect.from_event(event)
                    _LOGGER.debug("Received detection event: %s", detect)
                    # Forward the detection event to the Wyoming server
                    await self.write_event(detect.event())
                elif NotDetected.is_type(event.type):
                    not_detected = NotDetected.from_event(event)
                    _LOGGER.debug(
                        "Received not detected event: %s", not_detected)
                    # Forward the not detected event to the Wyoming server
                    await self.write_event(not_detected.event())
                elif Describe.is_type(event.type):
                    describe = Describe.from_event(event)
                    _LOGGER.debug("Received describe event: %s", describe)
        except asyncio.CancelledError:
            _LOGGER.debug("Client listener task cancelled.")
            pass

    async def handle_event(self, event: Event) -> bool:
        """Handle Wyoming server events."""

        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Info sent to client")
            return True

        if Detect.is_type(event.type):
            detect = Detect.from_event(event)

            # Forward the detection event to the wake service
            _LOGGER.debug("Forwarding detection event to wake service")
            await self.wake_client.write_event(detect.event())

        elif AudioStart.is_type(event.type):
            audio_start = AudioStart.from_event(event)

            # Forward the audio start event to the wake service
            _LOGGER.debug("Forwarding audio start event to wake service")
            await self.wake_client.write_event(audio_start.event())

        elif AudioChunk.is_type(event.type):
            audio_chunk = AudioChunk.from_event(event)

            # Forward the audio chunk event to the wake service
            _LOGGER.debug("Forwarding audio chunk event to wake service")
            await self.wake_client.write_event(audio_chunk.event())
        elif AudioStop.is_type(event.type):
            audio_stop = AudioStop.from_event(event)

            # Forward the audio stop event to the wake service
            _LOGGER.debug("Forwarding audio stop event to wake service")
            await self.wake_client.write_event(audio_stop.event())
        else:
            _LOGGER.debug("Unexpected event: type=%s, data=%s",
                          event.type, event.data)

        return True
