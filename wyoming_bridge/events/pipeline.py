import asyncio
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Protocol
from dataclasses import dataclass

from wyoming.event import Event

from wyoming_bridge.connections.processor import ProcessorConnection
from wyoming_bridge.processors.types import ProcessorExtensions, ProcessorId, SubscriptionEventType


_LOGGER = logging.getLogger("bridge")

class EventDestination(Protocol):
    """Protocol for any destination that can receive Wyoming events."""
    
    async def write_event(self, event: Event) -> None:
        """Send event to the destination."""
        ...

@dataclass
class ProcessorEntry:
    processor_id: ProcessorId
    connection: ProcessorConnection

Subscriptions = Dict[SubscriptionEventType, List[ProcessorEntry]]

class Pipeline:
    """
    Handles the complete pipeline of an event from source to destination.
    
    This class encapsulates the logic for:
    1. Receiving source event
    2. Checking for blocking subscribers
    3. Processing blocking subscribers and collecting extensions
    4. Sending extensions to specific handler
    5. Sending to destination
    6. Sending to non-blocking subscribers
    """
    
    def __init__(
            self,
            destination: EventDestination,
            blocking_subscriptions: Subscriptions,
            non_blocking_subscriptions: Subscriptions,
            on_blocking_flow_complete: Optional[Callable[[ProcessorExtensions], Awaitable[None]]],
        ) -> None:
        self._destination = destination
        self._blocking_subscriptions: Subscriptions = blocking_subscriptions
        self._non_blocking_subscriptions: Subscriptions = non_blocking_subscriptions
        self._on_blocking_flow_complete = on_blocking_flow_complete
    
    async def process_event(self, event: Event) -> None:
        if not self._destination:
            _LOGGER.warning("No destination provided for event: %s", event.type)
            return
        
        blocking_subs = self._blocking_subscriptions.get(SubscriptionEventType(event.type), [])
        if blocking_subs:
            _LOGGER.debug("Found %d blocking subscribers for event %s.", len(blocking_subs), event.type)
            await self._handle_blocking_flow(event, blocking_subs)
        else:
            # No blocking subscriptions - send directly to destination
            await self._send_to_destination(event)
            
        # Always notify non-blocking subscribers
        await self._handle_non_blocking_flow(event)
    
    async def _handle_blocking_flow(self, event: Event, subscribers: List[ProcessorEntry]) -> None:
        collected_extensions: ProcessorExtensions = {}

        # Create tasks to send to all blocking subscribers in parallel
        async def send_to_processor(subscriber: ProcessorEntry) -> Optional[Event]:
            processor_id = subscriber.processor_id
            conn = subscriber.connection
            if not conn:
                _LOGGER.warning("Processor connection not found by id '%s'", processor_id)
                return None
            

            _LOGGER.debug("Sending event to blocking subscription '%s'.", processor_id)

            try:
                response = await conn.write_event(event, wait_for_response=True)
                _LOGGER.debug("Received response from blocking subscription '%s': %s", processor_id, response)
                if response:
                    return response
                else:
                    _LOGGER.warning("No response received from blocking subscription '%s'", processor_id)
                    return None
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for response from blocking subscription '%s'", processor_id)
                return None
            except ConnectionError:
                _LOGGER.warning("Connection error with blocking subscription '%s'", processor_id)
                return None
            except Exception:
                _LOGGER.exception("Failed to send event to blocking subscription '%s'", processor_id)
                return None

        # Send to all processors in parallel
        tasks = [send_to_processor(sub) for sub in subscribers]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process all responses
        for response in responses:
            if not isinstance(response, Event):
                _LOGGER.warning("Response from blocking subscription is not an Event: %r", response)
                continue

            ext = response.data.get("ext", {}) if response.data else {}
            collected_extensions.update(ext)
        
        # Call the on_blocking_flow_complete callback if provided
        if self._on_blocking_flow_complete and collected_extensions:
            await self._on_blocking_flow_complete(collected_extensions)
        
        await self._send_to_destination(event)

    async def _handle_non_blocking_flow(self, event: Event) -> None:
        """Notify non-blocking subscribers for an event."""
        
        non_blocking_subs = self._non_blocking_subscriptions.get(SubscriptionEventType(event.type), [])
        if non_blocking_subs:
            _LOGGER.debug("Notifying %d non-blocking subscribers for event %s.", len(non_blocking_subs), event.type)
            
            # Create tasks to send event to all non-blocking subscribers
            tasks = []
            for sub in non_blocking_subs:
                conn = sub.connection
                if conn:
                    task = asyncio.create_task(
                        conn.write_event(event),
                        name=f"non_blocking_{sub.processor_id}_{event.type}"
                    )
                    tasks.append(task)
                else:
                    _LOGGER.warning("Processor connection not found for %s", sub.processor_id)
            
            # Wait for all non-blocking notifications to complete (fire and forget)
            if tasks:
                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    _LOGGER.debug("Sent event to %d non-blocking subscribers", len(tasks))
                except Exception:
                    _LOGGER.exception("Error sending event to non-blocking subscribers")
    
    async def _send_to_destination(self, event: Event) -> None:
        try:
            await self._destination.write_event(event)
        except Exception:
            _LOGGER.exception("Failed to send event to destination: %s", event.type)
    