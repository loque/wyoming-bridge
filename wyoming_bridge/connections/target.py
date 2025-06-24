from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Awaitable, Callable

from wyoming.audio import AudioChunk
from wyoming.client import AsyncClient
from wyoming.event import Event


_LOGGER = logging.getLogger("conns")

class WyomingTargetConnection(ABC):
    TARGET_TYPE: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "TARGET_TYPE", "") == "":
            raise TypeError(
                f"{cls.__name__} must define a class attribute TARGET_TYPE"
            )
        
    def __init__(self, uri: str, on_target_event: Callable[[Event], Awaitable[None]]):
        self._type = self.TARGET_TYPE
        self._uri = uri
        self.on_target_event = on_target_event

        self._client = None
        self._is_connected = False
        self._write_lock = asyncio.Lock()

    async def _connect(self):
        try:
            _LOGGER.debug("Connecting to target '%s': %s", self._type, self._uri)
            self._client = AsyncClient.from_uri(self._uri)
            await self._client.connect()
            self._is_connected = True
            
            # Start background task to listen to target events
            asyncio.create_task(self._listen_to_events())

            _LOGGER.info("Connected to target '%s'", self._type)

        except Exception:
            _LOGGER.exception("Failed to connect to target '%s'", self._type)
            await self._disconnect()
            raise
        
    async def _disconnect(self) -> None:
        self._is_connected = False

        if self._client:
            try:
                await self._client.disconnect()
                _LOGGER.debug("Disconnected from target '%s'", self._type)
            except Exception:
                _LOGGER.exception("Error disconnecting from target '%s'", self._type)
            finally:
                self._client = None

    async def _listen_to_events(self) -> None:
        """Background task to continuously listen to events from target."""
        if not self._client:
            return
            
        try:
            while self._is_connected and self._client:
                try:
                    event = await self._client.read_event()
                    if event is None:
                        _LOGGER.debug("Target connection closed")
                        raise
                    
                    # Handle target event
                    await self._on_target_event(event)

                    if callable(self.on_target_event):
                        await self.on_target_event(event)
                    
                except Exception:
                    _LOGGER.exception("Error reading from target '%s'", self._type)
                    raise
                    
        except Exception:
            _LOGGER.exception("Target reader task failed")
            await self._disconnect()
    
    async def write_event(self, event: Event) -> None:
        if not self._is_connected or not self._client:
            _LOGGER.debug("Target not connected")
            await self._connect()
            if not self._client:
                _LOGGER.error("Could not connect to target, cannot send event")
                return

        # Use lock to ensure thread-safe writing to target
        async with self._write_lock:
            try:
                if not AudioChunk.is_type(event.type):
                    _LOGGER.debug("Sending event to target '%s': %s", self._type, event.type)
                await self._client.write_event(event)
            except Exception:
                _LOGGER.exception("Failed to send event to target '%s'", self._type)
                # Disconnected to trigger reconnection
                await self._disconnect()
                return
            
    def is_connected(self) -> bool:
        return self._is_connected

    @abstractmethod
    async def _on_target_event(self, event: Event) -> None:
        """Handle events received from the target."""
        pass
    
    @staticmethod
    @abstractmethod
    def is_type(service_type: str | None) -> bool:
        pass

    @staticmethod
    def from_service_type(service_type: str | None) -> type["WyomingTargetConnection"]:
        from wyoming_bridge.connections.asr import WyomingAsrConnection
        from wyoming_bridge.connections.tts import WyomingTtsConnection
        from wyoming_bridge.connections.handle import WyomingHandleConnection
        from wyoming_bridge.connections.wake import WyomingWakeConnection

        subclasses = [
            WyomingAsrConnection,
            WyomingTtsConnection,
            WyomingHandleConnection,
            WyomingWakeConnection
            # Remaining target connection subclasses must be added here
        ]

        for subclass in subclasses:
            if subclass.is_type(service_type):
                return subclass
            
        raise ValueError(f"No target connection found for service type '{service_type}'")