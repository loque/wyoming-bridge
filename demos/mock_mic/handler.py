import asyncio
import logging

from wyoming.event import Event
from wyoming.server import AsyncEventHandler

from demos.mock_mic.streaming_server import StreamingServer
from demos.mock_mic.command_server import CommandServer

_LOGGER = logging.getLogger(__name__)

class EventHandler(AsyncEventHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._file_queue = asyncio.Queue()
        self._command_server = CommandServer(self._file_queue)
        self._streaming_server = StreamingServer(self._file_queue, self.write_event)
        _LOGGER.debug("EventHandler initialized")

    async def handle_event(self, event: Event) -> bool:
        """Output only"""
        return True

    async def disconnect(self) -> None:
        _LOGGER.debug("Client disconnected")
        
        # Disconnect command server
        command_server_success = await self._command_server.stop()
        if not command_server_success:
            _LOGGER.warning("Failed to properly disconnect command server")
        
        # Stop streaming server
        streaming_server_success = await self._streaming_server.stop()
        if not streaming_server_success:
            _LOGGER.warning("Failed to properly stop streaming server")


