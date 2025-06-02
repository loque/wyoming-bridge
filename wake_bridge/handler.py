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
    """Handle Wake Bridge events."""

    def __init__(self, wyoming_info: Info, target: AsyncClient, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.wyoming_info = wyoming_info
        self.wyoming_info_enriched = False
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
                    enriched_event = self._enrich_wyoming_info(event)
                    _LOGGER.debug("[TARGET] Event: %s", enriched_event.type)
                    await self.write_event(enriched_event)
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

    def _enrich_wyoming_info(self, event: Event) -> Event:
        """Enhance bridge info with target info."""
        if self.wyoming_info_enriched:
            return self.wyoming_info.event()

        target_info = Info.from_event(event)
        bridge = self.wyoming_info.wake[0]
        target = target_info.wake[0]

        bridge.name = (bridge.name or "") + (target.name or "")
        bridge.description = (bridge.description or "") + \
            (target.description or "")

        # Models assignment
        bridge.models = target.models

        self.wyoming_info_enriched = True
        return self.wyoming_info.event()

    async def handle_event(self, event: Event) -> bool:
        """Forward all events from the source to the target."""

        if AudioChunk.is_type(event.type) == False:
            # Avoid logging here because it can be very noisy
            _LOGGER.debug("[SOURCE] Event: %s", event.type)
            _LOGGER.debug("[SOURCE] Event data: %s", event.data)

        await self.target.write_event(event)

        return True
