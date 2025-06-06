import asyncio
import logging
import uuid
from typing import NewType, Optional, Dict, List, Set
from dataclasses import dataclass, field

from wyoming.audio import AudioChunk
from wyoming.event import Event
from wyoming.info import Info

from wyoming_bridge.info import enrich_wyoming_info
from wyoming_bridge.settings import BridgeSettings
from wyoming_bridge.connections import DownstreamConnection, UpstreamConnection
from wyoming_bridge.state_manager import LifecycleManager, BaseState
from wyoming_bridge.processors import Subscription, ProcessorId, SubscriptionEvent

_LOGGER = logging.getLogger(__name__)

CorrelationId = NewType('CorrelationId', str)


@dataclass
class ProcessorSubscription:
    """Enhanced subscription info with processor reference."""
    processor_id: ProcessorId
    subscription: Subscription


@dataclass
class EnrichmentTracker:
    """Tracks enrichment process for a correlation ID."""
    correlation_id: CorrelationId
    original_event: Event
    origin: str  # "source" or "target" to distinguish enrichment origin
    pending_enrichers: Set[CorrelationId] = field(default_factory=set)
    enriched_responses: Dict[CorrelationId, Event] = field(default_factory=dict)
    completed: bool = False


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

        # Track ongoing enrichment processes
        self._enrichment_trackers: Dict[CorrelationId, EnrichmentTracker] = {}

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
        await self._connect_downstream()
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

    async def _connect_downstream(self) -> None:
        """Connects to configured services."""

        # Start source connection
        await self._source_conn.start()

        # Start target connection if URI is provided
        if not self.settings.target.uri:
            # TODO: improve error handling
            raise ValueError("Target URI must be set in settings")

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
                name=f"processor_{processor_id}",
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
            correlation_id = self._generate_correlation_id()
            _LOGGER.debug("Starting enrichment process for source event %s with %d enrichers (%s)", event.type, len(source_enricher_subs), correlation_id)
            await self._notify_source_enrichers(event, correlation_id, source_enricher_subs)
        else:
            # No source enrichers - send directly to target and observers
            await self._publish_source_event(event)

    async def on_target_event(self, event: Event) -> None:
        """Called when an event is received from the target service."""

        if Info.is_type(event.type):
            event = enrich_wyoming_info(event)

        event_type = SubscriptionEvent(event.type)

        enricher_subs = self._enricher_subscriptions.get(event_type, [])
        target_enricher_subs = self._filter_subscriptions_by_origin(enricher_subs, "target")
        
        if target_enricher_subs:
            # Start enrichment process - send to enrichers and wait for all responses
            correlation_id = self._generate_correlation_id()
            _LOGGER.debug("Starting enrichment process for target event %s with %d enrichers (%s)", event.type, len(target_enricher_subs), correlation_id)
            
            await self._notify_target_enrichers(event, correlation_id, target_enricher_subs)
        else:
            # No target enrichers - send directly to source and observers
            await self._publish_target_event(event)

    async def on_processor_event(self, event: Event) -> None:
        """Called when an event is received from a processor (enricher responses)."""
        _LOGGER.debug("Event received from processor: %s", event.type)
        
        # Check if this is an enricher response by looking for correlation ID in event data
        # composed_correlation_id format: {correlation ID}_{processor ID}
        composed_correlation_id = self._extract_correlation_id(event)
        if not composed_correlation_id:
            _LOGGER.debug("Non-enricher processor event received: %s", event.type)
            return

        # Extract base correlation ID from the composed correlation ID and check if that's pending
        correlation_id = self._extract_base_correlation_id(composed_correlation_id)
        if correlation_id not in self._enrichment_trackers:
            _LOGGER.debug("No pending enrichment found for correlation_id %s", composed_correlation_id)
            return
        
        await self._handle_enricher_response(correlation_id, composed_correlation_id, event)
        
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

    def _generate_correlation_id(self) -> CorrelationId:
        """Generate a unique correlation ID for event tracking."""
        return CorrelationId(str(uuid.uuid4()))

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

    async def _notify_target_enrichers(self, event: Event, correlation_id: CorrelationId, enricher_subs: List[ProcessorSubscription]) -> None:
        """Send event to enricher processors and track the enrichment process."""
        # Create enrichment tracker
        tracker = EnrichmentTracker(
            correlation_id=correlation_id,
            original_event=event,
            origin="target",
            pending_enrichers=set(),
            enriched_responses={},
            completed=False
        )
        
        # Send to all enricher processors
        for proc_sub in enricher_subs:
            processor_conn = self._processor_connections.get(proc_sub.processor_id)
            if not processor_conn:
                _LOGGER.warning("Processor connection not found for enricher %s", proc_sub.processor_id)
                continue

            # Create composed correlation ID for the event to enrich
            composed_correlation_id = CorrelationId(f"{correlation_id}_{proc_sub.processor_id}")
            event_to_enrich = self._add_correlation_id(event, composed_correlation_id)
            
            # Track this enricher as pending
            tracker.pending_enrichers.add(composed_correlation_id)
            
            _LOGGER.debug("Sending event to enricher %s with correlation_id %s", proc_sub.processor_id, composed_correlation_id)
            
            try:
                await processor_conn.send_event(event_to_enrich)
            except Exception:
                _LOGGER.exception("Failed to send event to enricher %s", proc_sub.processor_id)
                # Remove from pending since it failed
                tracker.pending_enrichers.discard(composed_correlation_id)
                
        
        # Store the tracker
        self._enrichment_trackers[correlation_id] = tracker
        
        # If no enrichers were successfully contacted, finalize immediately
        if not tracker.pending_enrichers:
            _LOGGER.debug("No enrichers available, finalizing event immediately")
            await self._publish_target_event(event)
            del self._enrichment_trackers[correlation_id]

    async def _notify_source_enrichers(self, event: Event, correlation_id: CorrelationId, enricher_subs: List[ProcessorSubscription]) -> None:
        """Send event to enricher processors and track the enrichment process for source events."""
        # Create enrichment tracker
        tracker = EnrichmentTracker(
            correlation_id=correlation_id,
            original_event=event,
            origin="source",
            pending_enrichers=set(),
            enriched_responses={},
            completed=False
        )
        
        # Send to all enricher processors
        for proc_sub in enricher_subs:
            processor_conn = self._processor_connections.get(proc_sub.processor_id)
            if not processor_conn:
                _LOGGER.warning("Processor connection not found for enricher %s", proc_sub.processor_id)
                continue

            # Create composed correlation ID for the event to enrich
            composed_correlation_id = CorrelationId(f"{correlation_id}_{proc_sub.processor_id}")
            event_to_enrich = self._add_correlation_id(event, composed_correlation_id)
            
            # Track this enricher as pending
            tracker.pending_enrichers.add(composed_correlation_id)
            
            _LOGGER.debug("Sending event to enricher %s with correlation_id %s", proc_sub.processor_id, composed_correlation_id)
            
            try:
                await processor_conn.send_event(event_to_enrich)
            except Exception:
                _LOGGER.exception("Failed to send event to enricher %s", proc_sub.processor_id)
                # Remove from pending since it failed
                tracker.pending_enrichers.discard(composed_correlation_id)
                
        
        # Store the tracker
        self._enrichment_trackers[correlation_id] = tracker
        
        # If no enrichers were successfully contacted, finalize immediately
        if not tracker.pending_enrichers:
            _LOGGER.debug("No enrichers available, finalizing event immediately")
            await self._publish_source_event(event)
            del self._enrichment_trackers[correlation_id]

    async def _handle_enricher_response(self, correlation_id: CorrelationId, composed_correlation_id: CorrelationId, enricher_event: Event) -> None:
        """Handle response from enricher processor."""
        tracker = self._enrichment_trackers.get(correlation_id)
        if not tracker:
            _LOGGER.warning("Received enricher response for unknown base correlation_id: %s", correlation_id)
            return
        
        if tracker.completed:
            _LOGGER.debug("Enricher response received after completion for correlation_id: %s", correlation_id)
            return
        
        # Store the enricher response
        tracker.enriched_responses[composed_correlation_id] = enricher_event
        tracker.pending_enrichers.discard(composed_correlation_id)
        
        _LOGGER.debug("Received enricher response. Pending: %d, Received: %d", len(tracker.pending_enrichers), len(tracker.enriched_responses))
        
        # Check if all enrichers have responded
        if not tracker.pending_enrichers:
            await self._complete_enrichment(correlation_id, tracker)

    async def _complete_enrichment(self, correlation_id: CorrelationId, tracker: EnrichmentTracker) -> None:
        """Complete enrichment process by merging responses and finalizing event."""
        _LOGGER.debug("Completing enrichment for correlation_id: %s with %d responses", correlation_id, len(tracker.enriched_responses))
        
        # Merge enricher responses with original event
        enriched_event = self._merge_enricher_responses(tracker.original_event, tracker.enriched_responses)
        
        # Mark as completed
        tracker.completed = True
        
        # Finalize the enriched event based on origin
        if tracker.origin == "source":
            await self._publish_source_event(enriched_event)
        else:  # target
            await self._publish_target_event(enriched_event)
        
        # Clean up tracker
        del self._enrichment_trackers[correlation_id]

    async def _publish_target_event(self, event: Event) -> None:
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

    async def _publish_source_event(self, event: Event) -> None:
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

    def _extract_correlation_id(self, event: Event) -> Optional[CorrelationId]:
        """Extract correlation ID from event data."""
        if not event.data:
            return None
        
        correlation_id_str = event.data.get("correlation_id")
        if correlation_id_str:
            return CorrelationId(correlation_id_str)
        
        return None

    def _extract_base_correlation_id(self, composed_correlation_id: CorrelationId) -> CorrelationId:
        """Extract base correlation ID from enricher-specific correlation ID."""
        # composed_correlation_id format: {correlation ID}_{processor ID}
        parts = composed_correlation_id.rsplit('_', 1)
        if len(parts) > 1:
            return CorrelationId(parts[0])
        else:
            # Fallback - return the correlation_id as-is
            return composed_correlation_id

    def _merge_enricher_responses(self, original_event: Event, enriched_responses: Dict[CorrelationId, Event]) -> Event:
        """Merge enricher responses with the original event."""
        if not enriched_responses:
            return original_event
        
        # Start with original event data
        merged_data = original_event.data.copy() if original_event.data else {}
        
        # Merge data from all enricher responses
        for enricher_event in enriched_responses.values():
            if not enricher_event.data:
                continue

            # Create a copy to avoid modifying original
            enricher_data = enricher_event.data.copy()
            
            # Shallow merge enricher data, overwriting existing keys
            for key, value in enricher_data.items():
                merged_data[key] = value

         # Remove correlation_id from final output
        merged_data.pop("correlation_id", None)

        # Create final enriched event
        enriched_event = Event.from_dict({
            "type": original_event.type,
            "data": merged_data
        })
        if original_event.payload:
            enriched_event.payload = original_event.payload
        
        _LOGGER.debug("Merged %d enricher responses into event %s", len(enriched_responses), original_event.type)
        
        return enriched_event
