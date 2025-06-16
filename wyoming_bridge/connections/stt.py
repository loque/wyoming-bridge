import logging

from wyoming.event import Event
from wyoming.asr import Transcript

from .target import WyomingTarget

_LOGGER = logging.getLogger("conns")

class WyomingSttTarget(WyomingTarget):

    def __init__(self, *args, **kwargs):
        super().__init__("stt", *args, **kwargs)

    @staticmethod
    def is_type(service_type: str | None) -> bool:
        if service_type is None:
            return False
        return service_type == "stt" or service_type == "asr"

    async def _on_target_event(self, event: Event) -> None:
        """Handle events received from the target."""
        _LOGGER.debug("Received event from target '%s': %s", self._type, event.type)

        if Transcript.is_type(event.type):
            await self._disconnect()
        
        # TODO: maybe this should be handled by _listen_to_events?
        await self._event_callback(event)