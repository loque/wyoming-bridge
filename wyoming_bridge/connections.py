"""Connection management abstractions for the Wyoming Bridge."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Protocol, Awaitable

from wyoming.client import AsyncClient
from wyoming.event import Event, async_write_event

_logger = logging.getLogger("conns")


class EventCallback(Protocol):
    """Protocol for event callback functions."""

    def __call__(self, event: Event) -> Awaitable[None]:
        """Handle an event."""
        ...


class ConnectionManager(ABC):
    """Abstract base class for managing connections."""

    def __init__(self, name: str):
        self.name = name
        self._task: Optional[asyncio.Task] = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Check if the connection is running."""
        return self._is_running

    async def start(self) -> None:
        """Start the connection manager."""
        if self._is_running:
            return

        self._is_running = True
        self._task = asyncio.create_task(
            self._run_loop(), name=f"{self.name}_connection")
        _logger.debug("Started %s connection manager", self.name)

    async def stop(self) -> None:
        """Stop the connection manager."""
        self._is_running = False

        if self._task is not None:
            _logger.debug("Stopping %s connection manager", self.name)
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await self._cleanup()
        _logger.debug("Stopped %s connection manager", self.name)

    @abstractmethod
    async def _run_loop(self) -> None:
        """Main connection loop."""
        pass

    @abstractmethod
    async def _cleanup(self) -> None:
        """Clean up resources."""
        pass


class DownstreamConnection(ConnectionManager):
    """Manages downstream connections (e.g., wake word detection)."""

    def __init__(
        self,
        name: str,
        uri: str,
        reconnect_seconds: float,
        event_callback: EventCallback
    ):
        super().__init__(name)
        self.uri = uri
        self.reconnect_seconds = reconnect_seconds
        self.event_callback = event_callback
        self._client: Optional[AsyncClient] = None
        self._send_queue: Optional[asyncio.Queue[Event]] = None

    async def send_event(self, event: Event) -> None:
        """Send an event downstream."""
        if self._send_queue is not None:
            self._send_queue.put_nowait(event)

    async def _run_loop(self) -> None:
        """Main downstream connection loop."""
        while self._is_running:
            try:
                await self._connect_and_process()
            except asyncio.CancelledError:
                break
            except Exception:
                _logger.exception(
                    "Unexpected error in %s connection", self.name)
                await self._disconnect()
                if self._is_running:
                    await asyncio.sleep(self.reconnect_seconds)

    async def _connect_and_process(self) -> None:
        """Connect to downstream service and process events."""
        if self._client is None:
            self._client = AsyncClient.from_uri(self.uri)
            await self._client.connect()
            _logger.debug("Connected to %s service at %s", self.name, self.uri)

            # Reset queue
            self._send_queue = asyncio.Queue()

        # Process events bidirectionally
        send_task: Optional[asyncio.Task] = None
        receive_task: Optional[asyncio.Task] = None
        pending = set()

        while self._is_running and self._client is not None:
            # Read from queue to send downstream
            if send_task is None and self._send_queue is not None:
                send_task = asyncio.create_task(
                    self._send_queue.get(), name=f"{self.name}_send"
                )
                pending.add(send_task)

            # Read from downstream service
            if receive_task is None:
                receive_task = asyncio.create_task(
                    self._client.read_event(), name=f"{self.name}_receive"
                )
                pending.add(receive_task)

            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )

            # Handle send event
            if send_task in done:
                assert send_task is not None
                event = send_task.result()
                send_task = None
                if event.type != "audio-chunk":
                    _logger.debug("Sending event down to %s: %s",
                                  self.name, event.type)
                await self._client.write_event(event)

            # Handle receive event
            if receive_task in done:
                assert receive_task is not None
                event = receive_task.result()
                receive_task = None

                if event is None:
                    _logger.warning("%s service disconnected", self.name)
                    await self._disconnect()
                    await asyncio.sleep(self.reconnect_seconds)
                    break

                _logger.debug("Received event from %s: %s",
                              self.name, event.type)
                await self.event_callback(event)

    async def _disconnect(self) -> None:
        """Disconnect from downstream service."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass  # Ignore disconnect errors
            self._client = None

    async def _cleanup(self) -> None:
        """Clean up downstream connection resources."""
        await self._disconnect()


class UpstreamConnection(ConnectionManager):
    """Manages upstream connection (e.g., Home Assistant via event handler)."""

    def __init__(self, name: str):
        super().__init__(name)
        self.event_handler_id: Optional[str] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def connect_event_handler(self, event_handler_id: str, writer: asyncio.StreamWriter) -> None:
        """Connect an event handler."""
        self.event_handler_id = event_handler_id
        self._writer = writer
        _logger.debug("Event handler connected to %s: %s",
                      self.name, event_handler_id)

    async def disconnect_event_handler(self) -> None:
        """Disconnect the current event handler."""
        self.event_handler_id = None
        self._writer = None
        _logger.debug("Event handler disconnected from %s", self.name)

    async def send_event(self, event: Event) -> None:
        """Send an event to the upstream."""
        if self._writer is None:
            return

        try:
            _logger.debug("Sending event up to %s: %s", self.name, event.type)
            await async_write_event(event, self._writer)
        except Exception as err:
            await self.disconnect_event_handler()

            if isinstance(err, ConnectionResetError):
                _logger.warning(
                    "Event handler disconnected unexpectedly from %s", self.name)
            else:
                _logger.exception(
                    "Unexpected error sending event up to %s", self.name)

    @property
    def is_connected(self) -> bool:
        """Check if source is connected."""
        return self._writer is not None

    async def _run_loop(self) -> None:
        """Source doesn't need a continuous loop - events come via handler."""
        # Just wait until stopped
        while self._is_running:
            await asyncio.sleep(1)

    async def _cleanup(self) -> None:
        """Clean up source connection resources."""
        await self.disconnect_event_handler()
