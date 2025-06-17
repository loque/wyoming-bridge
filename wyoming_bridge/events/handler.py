import logging
import time

from wyoming.event import Event
from wyoming.server import AsyncEventHandler

from wyoming_bridge.core.bridge import WyomingBridge

_LOGGER = logging.getLogger("main")

class WyomingEventHandler(AsyncEventHandler):
    def __init__(self, bridge: WyomingBridge, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.bridge = bridge
        self.event_handler_id = str(time.monotonic_ns())

    async def handle_event(self, event: Event) -> bool:
        """Forward all events from the server to the bridge."""

        # If there is no active connection, or if this is a new connection
        # taking over, (re)establish the upstream connection.
        if self.bridge.event_handler_id is None or \
           self.bridge.event_handler_id != self.event_handler_id:
            _LOGGER.debug(
                "New event handler taking over or first connection. Old ID: %s, New ID: %s",
                self.bridge.event_handler_id,
                self.event_handler_id
            )
            await self.bridge.bind_server_handler(self.event_handler_id, self.writer)
            
        # If self.bridge.event_handler_id == self.event_handler_id, it means this is the
        # current, recognized handler, so we just proceed.

        await self.bridge.on_server_event(event)
        return True
