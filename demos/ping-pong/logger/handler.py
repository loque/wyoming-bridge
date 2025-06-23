import logging

from wyoming.event import Event
from wyoming.server import AsyncEventHandler

_LOGGER = logging.getLogger(__name__)

class EventHandler(AsyncEventHandler):
    """Handle Wyoming events."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)


    async def handle_event(self, event: Event) -> bool:
        """Handle all Wyoming events."""
        
        _LOGGER.info("Logging event [%s]: %s", event.type, event.data)
        return True
