import asyncio
import logging
import uuid
from typing import NewType, Optional, Dict, List, Set
from dataclasses import dataclass
import requests

from wyoming.audio import AudioChunk
from wyoming.event import Event
from wyoming.info import Info

from wyoming_bridge.info import enrich_wyoming_info
from wyoming_bridge.settings import BridgeSettings
from wyoming_bridge.connections import DownstreamConnection, UpstreamConnection
from wyoming_bridge.state_manager import LifecycleManager, BaseState
from wyoming_bridge.processors import Subscription, ProcessorId, SubscriptionEvent

_LOGGER = logging.getLogger("bridge")

CorrelationId = NewType('CorrelationId', str)


@dataclass
class ProcessorSubscription:
    """Enhanced subscription info with processor reference."""
    processor_id: ProcessorId
    subscription: Subscription


@dataclass
class ProcessorResponseEntry:
    """Response from a processor containing the new data it added."""
    processor_id: ProcessorId
    data: Dict[str, str]


class ProcessorTracker:
    """Tracks processors for a correlation ID."""
    
    def __init__(self, original_event: Event, origin: str):
        """Initialize the processor tracker.
        
        Args:
            original_event: The original event being processed
            origin: "source" or "target" to distinguish processing origin
        """
        self.correlation_id = CorrelationId(str(uuid.uuid4()))
        self.original_event = original_event
        self.origin = origin
        self.pending_processors: Set[ProcessorId] = set()
        self.processor_responses: List[ProcessorResponseEntry] = []
        self.completed = False
    
    def track_processor(self, processor_id: ProcessorId) -> None:
        """Add a processor to the pending list."""
        self.pending_processors.add(processor_id)
    
    def finalize_processor(self, processor_id: ProcessorId, data: Dict[str, str]) -> None:
        """Add a processor response and remove from pending."""
        response = ProcessorResponseEntry(processor_id=processor_id, data=data)
        self.processor_responses.append(response)
        # Remove the corresponding pending processor
        self.pending_processors.discard(response.processor_id)
    
    def remove_failed_processor(self, processor_id: ProcessorId) -> None:
        """Remove a failed processor from pending list."""
        self.pending_processors.discard(processor_id)
    
    def is_complete(self) -> bool:
        """Check if all processors have responded or failed."""
        return len(self.pending_processors) == 0
    
    def get_processed_data(self) -> Dict[str, str]:
        """Get all processed data merged together."""
        merged_data = {}
        for response in self.processor_responses:
            # Merge processor data, overwriting existing keys
            for key, value in response.data.items():
                merged_data[key] = value
        return merged_data
    
    def get_processed_event(self) -> Event:
        """Get the original event with all processed data merged in."""
        if not self.processor_responses:
            return self.original_event
        
        # Start with original event data
        merged_data = self.original_event.data.copy() if self.original_event.data else {}

        # Merge all processed data
        processed_data = self.get_processed_data()
        merged_data.update(processed_data)

        # Remove correlation_id and processor_id from final output
        merged_data.pop("correlation_id", None)
        merged_data.pop("processor_id", None)

        # Create final processed event
        processed_event = Event.from_dict({
            "type": self.original_event.type,
            "data": merged_data
        })
        if self.original_event.payload:
            processed_event.payload = self.original_event.payload

        return processed_event


class WyomingBridge(LifecycleManager):
    """
    WyomingBridge serves as a bridge between the Wyoming target and the source
    (e.g.  Home Assistant).
    """

    def __init__(self, settings: BridgeSettings) -> None:
        """Initializes the WyomingBridge with state management."""
        super().__init__("wyoming_bridge")
        _LOGGER.debug("Initializing WyomingBridge with settings: %s", settings)
        self.settings = settings

        # Connection managers
        self._source_conn = UpstreamConnection("source")
        self._target_conn: Optional[DownstreamConnection] = None

        # Processor connections and subscriptions
        self._processor_connections: Dict[ProcessorId, DownstreamConnection] = {}
        self._enricher_subscriptions: Dict[SubscriptionEvent, List[ProcessorSubscription]] = {}
        self._observer_subscriptions: Dict[SubscriptionEvent, List[ProcessorSubscription]] = {}

        # Track processors progress
        self._processor_trackers: Dict[CorrelationId, ProcessorTracker] = {}

        # Initialize subscription indexes
        self._build_subscription_indexes()

    @property
    def event_handler_id(self) -> Optional[str]:
        """Get current event handler ID."""
        return self._source_conn.event_handler_id

    async def run(self) -> None:
        """Run main bridge loop using state machine."""
        while self.is_running:
            try:
                current_state = self.state

                if current_state == BaseState.NOT_STARTED:
                    await self.start()
                elif current_state in (BaseState.STOPPED,):
                    break
                else:
                    # Wait for state changes
                    await self.wait_for_state_change()

            except Exception:
                if self.is_running:
                    # Automatically restart on unexpected errors
                    _LOGGER.exception("Unexpected error running bridge")
                    await self.restart()

    # Lifecycle state handlers
    async def _on_starting(self) -> None:
        """Handle STARTING state."""
        await self._connect_services()
        await self._state_machine.transition_to(BaseState.STARTED)

    async def _on_started(self) -> None:
        """Handle STARTED state - bridge is operational."""
        _LOGGER.info("Wyoming bridge started successfully")

    async def _on_stopping(self) -> None:
        """Handle STOPPING state."""
        await self._disconnect_downstream()
        await self._state_machine.transition_to(BaseState.STOPPED)

    async def _on_stopped(self) -> None:
        """Handle STOPPED state - bridge is fully stopped."""
        _LOGGER.info("Wyoming bridge stopped")

    async def _on_restarting(self) -> None:
        """Handle RESTARTING state."""
        await self._disconnect_downstream()

        _LOGGER.debug("Restarting bridge in %s second(s)", self.settings.restart_timeout)

        await asyncio.sleep(self.settings.restart_timeout)
        await self._state_machine.transition_to(BaseState.NOT_STARTED)

    # Connection management
    async def connect_upstream(self, event_handler_id: str, writer: asyncio.StreamWriter) -> None:
        """Set event writer."""
        await self._source_conn.connect_event_handler(event_handler_id, writer)

    async def disconnect_upstream(self) -> None:
        """Remove writer."""
        await self._source_conn.disconnect_event_handler()

    async def _connect_services(self) -> None:
        """Connects to configured services."""

        # Start source connection
        await self._source_conn.start()

        # Start target connection
        _LOGGER.debug("Connecting to target service: %s", self.settings.target.uri)
        self._target_conn = DownstreamConnection(
            name="target",
            uri=self.settings.target.uri,
            reconnect_seconds=self.settings.target.reconnect_seconds,
            event_callback=self.on_target_event
        )
        await self._target_conn.start()

        # Connect to all configured processors
        await self._connect_processors()

    async def _connect_processors(self) -> None:
        """Establish connections to all configured processors."""
        for processor in self.settings.processors:
            processor_id = ProcessorId(processor["id"])
            processor_uri = processor["uri"]

            _LOGGER.debug("Connecting to processor %s at %s", processor_id, processor_uri)

            processor_conn = DownstreamConnection(
                name=processor_id,
                uri=processor_uri,
                # TODO: processors may have their own reconnect settings
                reconnect_seconds=self.settings.target.reconnect_seconds,
                event_callback=self.on_processor_event
            )

            self._processor_connections[processor_id] = processor_conn
            await processor_conn.start()

        _LOGGER.info("Connected to %d processors", len(self._processor_connections))

    async def _disconnect_downstream(self) -> None:
        """Disconnects from running services."""
        # Stop processor connections
        await self._disconnect_processors()

        # Stop target connection
        if self._target_conn is not None:
            await self._target_conn.stop()
            self._target_conn = None

        # Stop source connection manager
        await self._source_conn.stop()

        _LOGGER.debug("Disconnected from services")

    async def _disconnect_processors(self) -> None:
        """Disconnect from all processor connections."""
        for processor_id, connection in self._processor_connections.items():
            _LOGGER.debug("Disconnecting from processor %s", processor_id)
            await connection.stop()

        self._processor_connections.clear()
        _LOGGER.debug("Disconnected from all processors")

    def _filter_subscriptions_by_origin(self, subscriptions: List[ProcessorSubscription], origin: str) -> List[ProcessorSubscription]:
        """Filter subscriptions by the specified origin."""
        return [sub for sub in subscriptions if sub.subscription.get("origin") == origin]

    # Event handling
    async def on_source_event(self, event: Event) -> None:
        """Called when an event is received from source."""

        if self._target_conn is None:
            # TODO: improve error handling
            raise RuntimeError("Target connection is not established")

        if not AudioChunk.is_type(event.type):
            _LOGGER.debug("Event received from source: %s", event.type)

        event_type = SubscriptionEvent(event.type)
        
        # Check for enricher subscriptions for source events
        enricher_subs = self._enricher_subscriptions.get(event_type, [])
        source_enricher_subs = self._filter_subscriptions_by_origin(enricher_subs, "source")
        
        if source_enricher_subs:
            # Start enrichment process - send to enrichers and wait for all responses
            _LOGGER.debug("Starting enrichment process for source event %s with %d enrichers", event.type, len(source_enricher_subs))
            await self._send_to_pre_processors(event, source_enricher_subs)
        else:
            # No source enrichers - send directly to target and observers
            await self._send_to_target(event)

    async def on_target_event(self, event: Event) -> None:
        """Called when an event is received from the target service."""

        if Info.is_type(event.type):
            event = enrich_wyoming_info(event)

        event_type = SubscriptionEvent(event.type)

        enricher_subs = self._enricher_subscriptions.get(event_type, [])
        target_enricher_subs = self._filter_subscriptions_by_origin(enricher_subs, "target")
        
        if target_enricher_subs:
            # Start enrichment process - send to enrichers and wait for all responses
            _LOGGER.debug("Starting enrichment process for target event %s with %d enrichers", event.type, len(target_enricher_subs))
            
            await self._send_to_post_processors(event, target_enricher_subs)
        else:
            # No target enrichers - send directly to source and observers
            await self._send_to_source(event)

    async def on_processor_event(self, event: Event) -> None:
        """Called when an event is received from a processor (enricher responses)."""
        _LOGGER.debug("Event received from processor: %s", event.type)
        
        # Check if this is an enricher response by looking for correlation ID in event data
        correlation_id = self._read_correlation_id(event)
        if not correlation_id:
            _LOGGER.debug("Non-enricher processor event received: %s", event.type)
            return

        # Check if this correlation ID has a pending enrichment
        if correlation_id not in self._processor_trackers:
            _LOGGER.debug("No pending enrichment found for correlation_id %s", correlation_id)
            return
        
        await self._handle_processor_response(correlation_id, event)
        
    def _build_subscription_indexes(self) -> None:
        """Build indexed lookups for processor subscriptions."""
        self._enricher_subscriptions.clear()
        self._observer_subscriptions.clear()

        for processor in self.settings.processors:
            for subscription in processor["subscriptions"]:
                event_type_str = subscription.get("event", "")
                if not event_type_str:
                    continue

                # Convert to proper types
                event_type = SubscriptionEvent(event_type_str)
                processor_id = ProcessorId(processor["id"])

                processor_sub = ProcessorSubscription(
                    processor_id=processor_id,
                    subscription=subscription
                )

                role = subscription.get("role", "observer")
                if role == "enricher":
                    if event_type not in self._enricher_subscriptions:
                        self._enricher_subscriptions[event_type] = []
                    self._enricher_subscriptions[event_type].append(processor_sub)
                else:  # observer
                    if event_type not in self._observer_subscriptions:
                        self._observer_subscriptions[event_type] = []
                    self._observer_subscriptions[event_type].append(processor_sub)

    async def _send_to_observers(self, event: Event, observer_subs: List[ProcessorSubscription]) -> None:
        """Send event to observer processors in parallel."""
        if not observer_subs:
            return

        # Create tasks to send event to all observer processors
        tasks = []
        for proc_sub in observer_subs:
            processor_conn = self._processor_connections.get(proc_sub.processor_id)
            if processor_conn:
                task = asyncio.create_task(
                    processor_conn.send_event(event),
                    name=f"observer_{proc_sub.processor_id}_{event.type}"
                )
                tasks.append(task)
            else:
                _LOGGER.warning("Processor connection not found for %s", proc_sub.processor_id)

        # Wait for all observer notifications to complete (fire and forget)
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                _LOGGER.debug("Sent event to %d observer processors", len(tasks))
            except Exception:
                _LOGGER.exception("Error sending event to observer processors")

    async def _send_to_post_processors(self, event: Event, enricher_subs: List[ProcessorSubscription]) -> None:
        """Send event to enricher processors and track the enrichment process."""
        # Create enrichment tracker
        tracker = ProcessorTracker(event, "target")
        correlation_id = tracker.correlation_id
        
        # Send to all enricher processors
        for proc_sub in enricher_subs:
            processor_conn = self._processor_connections.get(proc_sub.processor_id)
            if not processor_conn:
                _LOGGER.warning("Processor connection not found for enricher %s", proc_sub.processor_id)
                continue

            # Add correlation ID and processor ID to event for tracking
            event_to_enrich = self._add_correlation_and_processor_id(event, correlation_id, proc_sub.processor_id)
            
            # Track this enricher as pending
            tracker.track_processor(proc_sub.processor_id)
            
            _LOGGER.debug("Sending event to enricher %s with correlation_id %s", proc_sub.processor_id, correlation_id)
            
            try:
                await processor_conn.send_event(event_to_enrich)
            except Exception:
                _LOGGER.exception("Failed to send event to enricher %s", proc_sub.processor_id)
                # Remove from pending since it failed
                tracker.remove_failed_processor(proc_sub.processor_id)
                
        
        # Store the tracker
        self._processor_trackers[correlation_id] = tracker
        
        # If no enrichers were successfully contacted, finalize immediately
        if tracker.is_complete():
            _LOGGER.debug("No enrichers available, finalizing event immediately")
            await self._send_to_source(event)
            del self._processor_trackers[correlation_id]

    async def _send_to_pre_processors(self, event: Event, enricher_subs: List[ProcessorSubscription]) -> None:
        """Send event to enricher processors and track the enrichment process for source events."""
        # Create enrichment tracker
        tracker = ProcessorTracker(event, "source")
        correlation_id = tracker.correlation_id
        
        # Send to all enricher processors
        for proc_sub in enricher_subs:
            processor_conn = self._processor_connections.get(proc_sub.processor_id)
            if not processor_conn:
                _LOGGER.warning("Processor connection not found for enricher %s", proc_sub.processor_id)
                continue

            # Add correlation ID and processor ID to event for tracking
            event_to_enrich = self._add_correlation_and_processor_id(event, correlation_id, proc_sub.processor_id)
            
            # Track this enricher as pending
            tracker.track_processor(proc_sub.processor_id)
            
            _LOGGER.debug("Sending event to enricher %s with correlation_id %s", proc_sub.processor_id, correlation_id)
            
            try:
                await processor_conn.send_event(event_to_enrich)
            except Exception:
                _LOGGER.exception("Failed to send event to enricher %s", proc_sub.processor_id)
                # Remove from pending since it failed
                tracker.remove_failed_processor(proc_sub.processor_id)
                
        
        # Store the tracker
        self._processor_trackers[correlation_id] = tracker
        
        # If no enrichers were successfully contacted, finalize immediately
        if tracker.is_complete():
            _LOGGER.debug("No enrichers available, finalizing event immediately")
            await self._send_to_target(event)
            del self._processor_trackers[correlation_id]

    async def _handle_processor_response(self, correlation_id: CorrelationId, processor_event: Event) -> None:
        """Handle response from processor."""
        tracker = self._processor_trackers.get(correlation_id)
        if not tracker:
            _LOGGER.warning("Received processor response for unknown correlation_id: %s", correlation_id)
            return
        
        if tracker.completed:
            _LOGGER.debug("Processor response received after completion for correlation_id: %s", correlation_id)
            return

        # Extract processor ID from the processor response event data
        processor_id = processor_event.data.get("processor_id") if processor_event.data else None
        if not processor_id:
            _LOGGER.warning("Received processor response without processor_id for correlation_id: %s", correlation_id)
            return
        
        # Extract only the diff (new key-value pairs) from the processor response
        processor_diff = self._extract_processor_diff(tracker.original_event, processor_event)

        # Add the enriched response to the tracker (this also removes from pending)
        tracker.finalize_processor(processor_id, processor_diff)

        _LOGGER.debug("Received processor response from %s. Pending: %d/%d", processor_id, len(tracker.pending_processors), len(tracker.processor_responses))

        # Check if all processors have responded
        if tracker.is_complete():
            await self._complete_enrichment(correlation_id, tracker)

    async def _complete_enrichment(self, correlation_id: CorrelationId, tracker: ProcessorTracker) -> None:
        """Complete enrichment process by merging responses and finalizing event."""
        _LOGGER.debug("Completing enrichment for correlation_id: %s with %d response(s)", correlation_id, len(tracker.processor_responses))
        
        # Mark as completed
        tracker.completed = True
        
        # Finalize the enriched event based on origin
        if tracker.origin == "source":
            # To target
            enriched_event = tracker.get_processed_event()
            await self._send_to_target(enriched_event)
        else:
            # To source
            self._update_all_input_text(tracker.get_processed_data())
            await self._send_to_source(tracker.original_event)
        
        # Clean up tracker
        del self._processor_trackers[correlation_id]

    async def _send_to_source(self, event: Event) -> None:
        """Send final event to source and target observers."""
        # Forward event to source
        await self._source_conn.send_event(event)
        
        # Notify observer subscribers for target events
        event_type = SubscriptionEvent(event.type)
        observer_subs = self._observer_subscriptions.get(event_type, [])
        target_observer_subs = self._filter_subscriptions_by_origin(observer_subs, "target")
        
        if target_observer_subs:
            _LOGGER.debug("Sending event to %d target observer processors for event %s", len(target_observer_subs), event.type)
            await self._send_to_observers(event, target_observer_subs)

    async def _send_to_target(self, event: Event) -> None:
        """Send enriched source event to target and source observers."""
        if self._target_conn is None:
            # TODO: improve error handling
            raise RuntimeError("Target connection is not established")
            
        # Send event to target service
        await self._target_conn.send_event(event)

        # Send event to observer processors for source events
        event_type = SubscriptionEvent(event.type)
        observer_subs = self._observer_subscriptions.get(event_type, [])
        source_observer_subs = self._filter_subscriptions_by_origin(observer_subs, "source")
        
        if source_observer_subs:
            if not AudioChunk.is_type(event.type):
                _LOGGER.debug("Sending event to %d source observer processors for event %s", len(source_observer_subs), event.type)
            await self._send_to_observers(event, source_observer_subs)

    def _add_correlation_id(self, event: Event, correlation_id: CorrelationId) -> Event:
        """Add correlation ID to event data."""
        # Create a new event with correlation_id in the data
        event_data = event.data.copy() if event.data else {}
        event_data["correlation_id"] = str(correlation_id)
        
        # Create new event with updated data
        new_event = Event.from_dict({
            "type": event.type,
            "data": event_data
        })
        if event.payload:
            new_event.payload = event.payload
        return new_event

    def _add_correlation_and_processor_id(self, event: Event, correlation_id: CorrelationId, processor_id: ProcessorId) -> Event:
        """Add correlation ID and processor ID to event data."""
        # Create a new event with correlation_id and processor_id in the data
        event_data = event.data.copy() if event.data else {}
        event_data["correlation_id"] = str(correlation_id)
        event_data["processor_id"] = str(processor_id)
        
        # Create new event with updated data
        new_event = Event.from_dict({
            "type": event.type,
            "data": event_data
        })
        if event.payload:
            new_event.payload = event.payload
        return new_event

    def _read_correlation_id(self, event: Event) -> Optional[CorrelationId]:
        """Read correlation ID from event data."""
        if not event.data:
            return None
        
        correlation_id_str = event.data.get("correlation_id")
        if correlation_id_str:
            return CorrelationId(correlation_id_str)
        
        return None

    def _update_input_text(self, key: str, value: str):
        url = f"{self.settings.hass_url}/api/services/input_text/set_value"
        data = {
            "entity_id": f"input_text.{key}",
            "value": value
        }
        headers = {
            "Authorization": f"Bearer {self.settings.hass_access_token}",
            "Content-Type": "application/json",
        }
        _LOGGER.debug("Updating input_text '%s' with value: %s. URL: %s, Data: %s, Headers: %s", key, value, url, data, headers)
        response = requests.post(url, headers=headers, json=data)
        try:
            if not response.ok:
                _LOGGER.error("Failed to update input_text '%s': %s", key, response.text)
            else:
                _LOGGER.debug("Input_text '%s' updated successfully. %s", key, response)
        except Exception as e:
            _LOGGER.exception("Exception while updating input_text '%s': %s", key, e)

    def _update_all_input_text(self, fields: Dict[str, str]) -> None:
        """Update Home Assistant input_text entities with processor data."""
        for key, value in fields.items():
            self._update_input_text(key, value)

    def _extract_processor_diff(self, original_event: Event, processor_event: Event) -> Dict[str, str]:
        """Extract only the new key-value pairs added by the processor."""
        if not processor_event.data:
            return {}
        
        # Get original event data
        original_data = original_event.data or {}
        processor_data = processor_event.data.copy()

        # Remove infrastructure fields as they're not enrichment
        processor_data.pop("correlation_id", None)
        processor_data.pop("processor_id", None)

        # Extract only the keys that are new or different from original
        diff = {}
        for key, value in processor_data.items():
            if key not in original_data or original_data[key] != value:
                # Only store string values as per requirement
                if isinstance(value, str):
                    diff[key] = value
                else:
                    # Convert non-string values to strings
                    diff[key] = str(value)
        
        return diff