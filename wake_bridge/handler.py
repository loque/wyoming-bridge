import asyncio
import logging

from wyoming.audio import AudioChunk
from wyoming.wake import Detect, NotDetected
from wyoming.info import Info
from wyoming.event import Event
from wyoming.client import AsyncClient
from wyoming.server import AsyncEventHandler

_LOGGER = logging.getLogger(__name__)


class WakeBridgeEventHandler(AsyncEventHandler):
    """Handle events from the Wake Bridge."""

    def __init__(
        self,
        target: AsyncClient,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.target = target
        self._target_listener_task = asyncio.create_task(
            self._listen_to_target())
        self._closed = False

    async def shutdown(self):
        """Cancel the target listener task and wait for it to finish."""
        if self._closed:
            return
        self._closed = True
        if self._target_listener_task:
            self._target_listener_task.cancel()
            try:
                await self._target_listener_task
            except asyncio.CancelledError:
                pass

    async def _listen_to_target(self):
        """Forward all events from the target to the source."""
        try:
            while True:
                event = await self.target.read_event()

                if event is None:
                    _LOGGER.debug("[TARGET] Disconnected")
                    break

                if Info.is_type(event.type):
                    # TODO: attach bridge and processors to the info event
                    _LOGGER.debug("[TARGET] Event: %s", event.type)
                    await self.write_event(event)
                elif Detect.is_type(event.type):
                    # TODO: notify the subscribed processors
                    _LOGGER.debug("[TARGET] Event: %s", event.type)
                    await self.write_event(event)

                elif NotDetected.is_type(event.type):
                    # TODO: notify the subscribed processors
                    _LOGGER.debug("[TARGET] Event: %s", event.type)
                    await self.write_event(event)

                else:
                    _LOGGER.debug("[TARGET] Event: %s", event.type)
                    _LOGGER.debug("[TARGET] Event data: %s", event.data)
                    await self.write_event(event)

        except asyncio.CancelledError:
            _LOGGER.debug("[TARGET] Listener task cancelled.")
            pass

    async def handle_event(self, event: Event) -> bool:
        """Forward all events from the source to the target."""

        if AudioChunk.is_type(event.type):
            # Avoid logging here because it can be very noisy
            await self.target.write_event(event)

        else:
            _LOGGER.debug("[SOURCE] Event: %s", event.type)
            _LOGGER.debug("[SOURCE] Event data: %s", event.data)

        return True
