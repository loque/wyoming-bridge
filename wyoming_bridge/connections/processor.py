import asyncio
import logging
from typing import Dict, Optional
import uuid

from wyoming.client import AsyncClient
from wyoming.event import Event

from wyoming_bridge.processors.types import ProcessorId

_LOGGER = logging.getLogger("conns")

class ProcessorConnection:
    def __init__(self, uri: str, processor_id: ProcessorId):
        self._uri = uri
        self._processor_id = processor_id
        
        self._client = None
        self._is_connected = False
        self._write_lock = asyncio.Lock()
        self._pending_responses: Dict[str, asyncio.Future[Event]] = {}
        self._listen_task: Optional[asyncio.Task] = None

    async def _connect(self):
        try:
            _LOGGER.debug("Connecting to processor '%s' at %s", self._processor_id, self._uri)
            self._client = AsyncClient.from_uri(self._uri)
            await self._client.connect()
            self._is_connected = True

            # Start background task to listen for responses
            self._listen_task = asyncio.create_task(
                self._listen_to_events(),
                name=f"processor_listener_{self._processor_id}"
            )

            _LOGGER.info("Connected to processor '%s'", self._processor_id)

        except Exception:
            _LOGGER.exception("Failed to connect to processor '%s'", self._processor_id)
            await self._disconnect()
            raise
    
    async def _disconnect(self) -> None:
        self._is_connected = False

        # Cancel listener task
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        self._listen_task = None

        # Cancel any pending response futures
        for future in self._pending_responses.values():
            if not future.done():
                future.cancel()
        self._pending_responses.clear()

        if self._client:
            try:
                await self._client.disconnect()
                _LOGGER.debug("Disconnected from processor '%s'", self._processor_id)
            except Exception:
                _LOGGER.exception("Error disconnecting from processor '%s'", self._processor_id)
            finally:
                self._client = None
    
    async def _listen_to_events(self):
        """Background task to read events from the processor and resolve pending futures."""
        if not self._client:
            return
            
        try:
            while self._is_connected and self._client:
                event = await self._client.read_event()
                if event is None:
                    _LOGGER.debug("Processor connection closed for '%s'", self._processor_id)
                    break
                    
                # Check for request_id in event.data
                request_id = event.data.get("request_id") if event.data else None
                if request_id and request_id in self._pending_responses:
                    future = self._pending_responses.pop(request_id)
                    if not future.done():
                        future.set_result(event)
                        _LOGGER.debug("Resolved response future for processor '%s' (request_id: %s)", self._processor_id, request_id)
                else:
                    _LOGGER.debug("Received event from processor '%s' without matching request_id: %s", self._processor_id, event.type)
                    
        except Exception:
            _LOGGER.exception("Error reading from processor '%s'", self._processor_id)
            await self._disconnect()
    
    async def write_event(self, event: Event, wait_for_response: bool = False, timeout: float = 30.0) -> Optional[Event]:
        if not self._is_connected or not self._client:
            _LOGGER.debug("Processor not connected")
            await self._connect()
            if not self._client:
                _LOGGER.error("Could not connect to processor, cannot send event")
                return
            
        response_future = None
        request_id = None
        
        if wait_for_response:
            # Generate request ID and attach to event
            request_id = str(uuid.uuid4())

            # Add request_id to event data
            if not hasattr(event, 'data'):
                event.data = {}
                
            event.data["request_id"] = request_id
            
            # Create a future to wait for the response
            response_future = asyncio.Future()
            self._pending_responses[request_id] = response_future

        # Use lock to ensure thread-safe writing to processor
        async with self._write_lock:
            try:
                _LOGGER.debug("Sending event '%s' to processor '%s' (request_id: %s)", event.type, self._processor_id, request_id)
                await self._client.write_event(event)
            except Exception:
                _LOGGER.exception("Failed to send event '%s' to processor '%s' (request_id: %s)", event.type, self._processor_id, request_id)

                # Clean up pending response if send failed
                self._cleanup_response(request_id)

                # Disconnected to trigger reconnection
                await self._disconnect()
                return None
        
        # Ensure response_future is properly awaited and cleaned up
        if wait_for_response and response_future:
            try:
                response = await asyncio.wait_for(response_future, timeout=timeout)
                if response is None:
                    _LOGGER.warning("Received empty response for event '%s' from processor '%s' (request_id: %s)", event.type, self._processor_id, request_id)
                return response
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for response for event '%s' from processor '%s' (request_id: %s)", event.type, self._processor_id, request_id)
                self._cleanup_response(request_id)
                return None
            except asyncio.CancelledError:
                _LOGGER.debug("Response wait for event '%s' cancelled for processor '%s' (request_id: %s)", event.type, self._processor_id, request_id)
                self._cleanup_response(request_id)
                return None
        
        return None

    def _cleanup_response(self, request_id: str | None):
        """Cleanup the response future for a given request ID."""
        if request_id and request_id in self._pending_responses:
            future = self._pending_responses.pop(request_id)
            if not future.done():
                future.cancel()