import logging
import time

from wyoming.event import Event
from wyoming.server import AsyncEventHandler

from wyoming_bridge.bridge import WakeBridge

_LOGGER = logging.getLogger(__name__)


class WakeBridgeEventHandler(AsyncEventHandler):
    """Handle Wake Bridge events."""

    def __init__(self, bridge: WakeBridge, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.bridge = bridge
        self.event_handler_id = str(time.monotonic_ns())

    async def handle_event(self, event: Event) -> bool:
        """Forward all events from the source to the bridge."""

        # Check if there is no active connection and take over as the event handler
        if self.bridge.event_handler_id is None:
            # Take over after a problem occurred
            await self.bridge.connect_upstream(self.event_handler_id, self.writer)
        elif self.bridge.event_handler_id != self.event_handler_id:
            # New connection
            _LOGGER.debug("Connection cancelled: %s", self.event_handler_id)
            return False

        await self.bridge.on_source_event(event)
        return True
