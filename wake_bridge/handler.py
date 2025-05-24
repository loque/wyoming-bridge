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
                    _LOGGER.debug("[CLIENT] Disconnected")
                    break  # Client disconnected

                if Detect.is_type(event.type):
                    _LOGGER.debug("[CLIENT] Event: %s", event.type)
                    await self.write_event(event)

                elif NotDetected.is_type(event.type):
                    _LOGGER.debug("[CLIENT] Event: %s", event.type)
                    await self.write_event(event)

                elif Describe.is_type(event.type):
                    _LOGGER.debug("[CLIENT] Event: %s", event.type)
                    await self.write_event(event)

                else:
                    _LOGGER.debug("[CLIENT] Unexpected event: type=%s, data=%s",
                                  event.type, event.data)
                    await self.write_event(event)

        except asyncio.CancelledError:
            _LOGGER.debug("Client listener task cancelled.")
            pass

    async def handle_event(self, event: Event) -> bool:
        """Handle Wyoming server events."""

        if Describe.is_type(event.type):
            _LOGGER.debug("[SERVER] Event: %s", event.type)
            await self.wake_client.write_event(event)

        elif Detect.is_type(event.type):
            _LOGGER.debug("[SERVER] Event: %s", event.type)
            await self.wake_client.write_event(event)

        elif AudioStart.is_type(event.type):
            _LOGGER.debug("[SERVER] Event: %s", event.type)
            await self.wake_client.write_event(event)

        elif AudioChunk.is_type(event.type):
            # _LOGGER.debug("Forwarding audio chunk event to wake service")
            await self.wake_client.write_event(event)

        elif AudioStop.is_type(event.type):
            _LOGGER.debug("[SERVER] Event: %s", event.type)
            await self.wake_client.write_event(event)

        else:
            _LOGGER.debug("[SERVER] Unexpected event: type=%s, data=%s",
                          event.type, event.data)

        return True
