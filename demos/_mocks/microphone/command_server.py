import logging
from typing import Optional
import asyncio

_LOGGER = logging.getLogger(__name__)

class CommandServer:
    def __init__(self, file_queue: asyncio.Queue, host: str = "0.0.0.0", port: int = 10102) -> None:
        self._file_queue = file_queue
        self._host = host
        self._port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self._task = asyncio.create_task(self._start())

    async def _start(self) -> None:
        self._server = await asyncio.start_server(self._handle_command, self._host, self._port)
        _LOGGER.info("Command server listening on port %d", self._port)
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> bool:
        success = True

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for command server task to cancel")
                success = False
            self._task = None

        if self._server is not None:
            try:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
            except Exception as e:
                _LOGGER.error("Error closing command server: %s", e)
                success = False

        return success

    async def _handle_command(self, reader, writer) -> None:
        """Handle a single command from a client."""
        try:
            data = await reader.read(1024)
            filepath = data.decode()
            addr = writer.get_extra_info("peername")
            _LOGGER.debug(f"Received message from {addr}: {filepath}")

            filepath = filepath.strip()
            if not filepath:
                _LOGGER.warning("Received empty filepath")
                return

            await self._file_queue.put(filepath)
            _LOGGER.info("Queued for streaming: %s", filepath)
            writer.write(b"OK")
            await writer.drain()

        except Exception:
            _LOGGER.exception("Error processing command")
            writer.write(b"ERROR")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()