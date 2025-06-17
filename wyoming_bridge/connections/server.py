"""Connection management for the Wyoming Bridge server connection."""

import asyncio
import logging
from typing import Optional

from wyoming.event import Event, async_write_event

_LOGGER = logging.getLogger("conns")

class ServerConnection:
    def __init__(self):
        self.event_handler_id: Optional[str] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def bind_event_handler(self, event_handler_id: str, writer: asyncio.StreamWriter) -> None:
        self.event_handler_id = event_handler_id
        self._writer = writer
        _LOGGER.debug("Event handler connected.")

    async def unbind_event_handler(self) -> None:
        self.event_handler_id = None
        self._writer = None
        _LOGGER.debug("Event handler disconnected.")

    async def write_event(self, event: Event) -> None:
        if self._writer is None:
            return

        try:
            _LOGGER.debug("Sending event to server: %s, %s", event.type, event.data)
            await async_write_event(event, self._writer)
        except Exception as err:
            await self.unbind_event_handler()

            if isinstance(err, ConnectionResetError):
                _LOGGER.warning("Event handler disconnected unexpectedly")
            else:
                _LOGGER.exception("Unexpected error sending event to server")
