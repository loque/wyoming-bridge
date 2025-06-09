import logging

from wyoming.audio import AudioChunk
from wyoming.event import Event
from wyoming.server import AsyncEventHandler
from wyoming.wake import Detection
from wyoming.asr import Transcript

from .logger import configure_logger

_LOGGER = logging.getLogger("handler")
configure_logger("handler")

class EventHandler(AsyncEventHandler):
    """Handle Wyoming events."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)


    async def handle_event(self, event: Event) -> bool:
        """Handle all Wyoming events."""

        # Add a static speaker_id to Detection and Transcript events
        if Detection.is_type(event.type) or Transcript.is_type(event.type):
            _LOGGER.info("Logging event [%s]: %s", event.data, event.data)

            enriched_data = dict(event.data) if event.data else {}
            enriched_data["speaker_id"] = "static-speaker-1"

            enriched_event = Event(type=event.type, data=enriched_data, payload=event.payload)

            _LOGGER.info("Adding speaker_id to event [%s]: %s", enriched_event.type, enriched_event.data)
            await self.write_event(enriched_event)

            return True

        # Log the remaining Wyoming events excluding AudioChunk because it is
        # too verbose
        if not AudioChunk.is_type(event.type):
            _LOGGER.info("Logging event [%s]: %s", event.type, event.data)

        return True
