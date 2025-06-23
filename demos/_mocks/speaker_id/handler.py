import logging
import random

from wyoming.audio import AudioChunk
from wyoming.event import Event
from wyoming.server import AsyncEventHandler
from wyoming.wake import Detection
from wyoming.asr import Transcript

_LOGGER = logging.getLogger(__name__)

class EventHandler(AsyncEventHandler):
    """Handle Wyoming events."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)


    async def handle_event(self, event: Event) -> bool:
        """Handle all Wyoming events."""

        # Add a static speaker_id to Detection and Transcript events
        if Detection.is_type(event.type) or Transcript.is_type(event.type):
            _LOGGER.info("Logging event [%s]: %s", event.data, event.data)

            next_data = dict(event.data) if event.data else {}

            ext_value = next_data.get("ext")
            if not ext_value or not isinstance(ext_value, dict):
                next_data["ext"] = {}
            next_data["ext"]["speaker_id"] = random.choice(["adam", "alice", "bob", "charlie", "dave", "eve"])

            next_event = Event(type=event.type, data=next_data, payload=event.payload)

            _LOGGER.info("Adding speaker_id to event [%s]: %s", next_event.type, next_event.data)
            await self.write_event(next_event)

            return True

        # Log the remaining Wyoming events excluding AudioChunk because it is
        # too verbose
        if not AudioChunk.is_type(event.type):
            _LOGGER.info("Logging event [%s]: %s", event.type, event.data)

        return True
