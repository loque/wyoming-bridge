import logging

from wyoming.event import Event
from wyoming.server import AsyncEventHandler
from wyoming.wake import Detection

_logger = logging.getLogger(__name__)

class EventHandler(AsyncEventHandler):
    """Handle Wyoming events."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)


    async def handle_event(self, event: Event) -> bool:
        """Handle all Wyoming events."""

        # If detection, add speaker_id, send event, and log correlation_id
        if Detection.is_type(event.type):
            _logger.info("Logging event [detection]: %s", event.data)
            # Add speaker_id to event data
            new_data = dict(event.data) if event.data else {}
            new_data["speaker_id"] = "static-speaker-1"
            new_event = Event(type=event.type, data=new_data, payload=event.payload)
            await self.write_event(new_event)
            correlation_id = new_data.get("correlation_id")
            if correlation_id:
                _logger.info("detection correlation_id: %s", correlation_id)
            return True

        # Log the remaining Wyoming events
        _logger.info("Logging event [%s]: %s", event.type, event.data)

        return True
