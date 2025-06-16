import asyncio
import logging
import uuid
from typing import NewType, Optional, Dict, List, Set, Tuple
from dataclasses import dataclass
import requests

from wyoming.audio import AudioChunk
from wyoming.client import AsyncClient
from wyoming.event import Event
from wyoming.info import Describe, Info

from .connections.stt import WyomingSttTarget
from .connections.target import WyomingTarget
from .connections.manager import DownstreamConnection, UpstreamConnection
from .info import enrich_wyoming_info, read_service_type
from .settings import BridgeSettings
from .state_manager import LifecycleManager, BaseState
from .processors import Subscription, ProcessorId, SubscriptionEvent, SubscriptionMode, SubscriptionStage

_LOGGER = logging.getLogger("bridge")

TrackingId = NewType('TrackingId', str)
ProcessorExtensions = Dict[str, str]

@dataclass
class ProcessorResponse:
    tracking_id: TrackingId
    processor_id: ProcessorId
    ext: ProcessorExtensions
    event: Event

    @staticmethod
    def is_processor_response(event: Event) -> bool:
        return "ext" in event.data and "processor_id" in event.data and "tracking_id" in event.data
    
    @staticmethod
    def from_event(event: Event) -> "ProcessorResponse":
        """Create a ProcessorEvent from a standard Event."""
        if not ProcessorResponse.is_processor_response(event):
            raise ValueError("Event does not contain required processor fields")
        
        return ProcessorResponse(
            tracking_id=TrackingId(event.data["tracking_id"]),
            processor_id=ProcessorId(event.data["processor_id"]),
            ext=event.data.get("ext", {}),
            event=event,
        )


@dataclass
class ProcessorSubscription:
    """Enhanced subscription info with processor reference."""
    processor_id: ProcessorId
    subscription: Subscription


@dataclass
class ProcessorExtEntry:
    """Response from a processor containing the new data it added."""
    processor_id: ProcessorId
    ext: ProcessorExtensions


class ProcessorTracker:
    """Tracks processors for a correlation ID."""
    
    def __init__(self, original_event: Event, stage: SubscriptionStage):
        """Initialize the processor tracker."""
        self.tracking_id = TrackingId(str(uuid.uuid4()))
        self.original_event = original_event
        self.stage = stage
        self.pending_processors: Set[ProcessorId] = set()
        self.processor_extensions: List[ProcessorExtEntry] = []
    
    def track_processor(self, processor_id: ProcessorId) -> None:
        """Add a processor to the pending list."""
        self.pending_processors.add(processor_id)
    
    def finalize_processor(self, processor_id: ProcessorId, ext: ProcessorExtensions) -> None:
        """Add a processor response and remove from pending."""
        proc_ext = ProcessorExtEntry(processor_id=processor_id, ext=ext)
        self.processor_extensions.append(proc_ext)
        # Remove the corresponding pending processor
        self.pending_processors.discard(proc_ext.processor_id)
    
    def remove_failed_processor(self, processor_id: ProcessorId) -> None:
        """Remove a failed processor from pending list."""
        self.pending_processors.discard(processor_id)
    
    def is_complete(self) -> bool:
        """Check if all processors have responded or failed."""
        return len(self.pending_processors) == 0
    
    def get_extensions(self) -> ProcessorExtensions:
        """Get all processed extensions merged together."""
        merged_extensions: ProcessorExtensions = {}
        for response in self.processor_extensions:
            # Merge each processor's extensions into a single dictionary
            for key, value in response.ext.items():
                merged_extensions[key] = value
        return merged_extensions
    
    def get_processed_event(self) -> Event:
        """Get the original event with all processed extensions merged in."""
        if not self.processor_extensions:
            return self.original_event
        
        # Start with original event data
        merged_data = self.original_event.data.copy() if self.original_event.data else {}

        # Merge all processed extensions
        processed_extensions = self.get_extensions()
        merged_data.update(processed_extensions)

        # Remove tracking_id and processor_id from final output
        merged_data.pop("tracking_id", None)
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
    WyomingBridge serves as a bridge between the Wyoming target and the server
    (e.g.  Home Assistant).
    """

    def __init__(self, settings: BridgeSettings) -> None:
        """Initializes the WyomingBridge with state management."""
        super().__init__("wyoming_bridge")
        _LOGGER.debug("Initializing WyomingBridge with settings: %s", settings)
        self.settings = settings


        # Connection managers
        self._server = UpstreamConnection("server")
        self._target: Optional[WyomingTarget] = None
        self._processor_conns: Dict[ProcessorId, DownstreamConnection] = {}

        self._subscriptions: Dict[Tuple[SubscriptionEvent, SubscriptionStage, SubscriptionMode], List[ProcessorSubscription]] = {}
        self._processor_trackers: Dict[TrackingId, ProcessorTracker] = {}

        self._build_subscriptions_index()
    
    @property
    def event_handler_id(self) -> Optional[str]:
        """Get current event handler ID."""
        return self._server.event_handler_id

    def _build_subscriptions_index(self) -> None:
        """Build indexed lookups for processor subscriptions."""
        self._subscriptions.clear()

        for processor in self.settings.processors:
            for sub_config in processor["subscriptions"]:

                proc_sub = ProcessorSubscription(
                    processor_id=processor["id"],
                    subscription=sub_config
                )

                # Key: (SubscriptionEvent, SubscriptionStage, SubscriptionMode)
                key = (sub_config["event"], sub_config["stage"], sub_config["mode"])

                if key not in self._subscriptions:
                    self._subscriptions[key] = []
                self._subscriptions[key].append(proc_sub)

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

        # Start server connection
        await self._server.start()

        # Connect to all configured processors
        await self._connect_processors()

        await self._state_machine.transition_to(BaseState.STARTED)

    async def _on_started(self) -> None:
        """Handle STARTED state - bridge is operational."""
        _LOGGER.info("Wyoming bridge started successfully")

    async def _on_stopping(self) -> None:
        """Handle STOPPING state."""
        await self._disconnect_services()
        await self._state_machine.transition_to(BaseState.STOPPED)

    async def _on_stopped(self) -> None:
        """Handle STOPPED state - bridge is fully stopped."""
        _LOGGER.info("Wyoming bridge stopped")

    async def _on_restarting(self) -> None:
        """Handle RESTARTING state."""
        await self._disconnect_services()

        _LOGGER.debug("Restarting bridge in %s second(s)", self.settings.restart_timeout)

        await asyncio.sleep(self.settings.restart_timeout)
        await self._state_machine.transition_to(BaseState.NOT_STARTED)

    # Connection management
    async def connect_upstream(self, event_handler_id: str, writer: asyncio.StreamWriter) -> None:
        """Set event writer."""
        await self._server.connect_event_handler(event_handler_id, writer)

    async def disconnect_upstream(self) -> None:
        """Remove writer."""
        await self._server.disconnect_event_handler()

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

            self._processor_conns[processor_id] = processor_conn
            await processor_conn.start()

        _LOGGER.info("Connected to %d processors", len(self._processor_conns))

    async def _disconnect_services(self) -> None:
        """Disconnects from running services."""
        # Stop processor connections
        await self._disconnect_processors()

        # Stop server connection manager
        await self._server.stop()

        _LOGGER.debug("Disconnected from services")

    async def _disconnect_processors(self) -> None:
        """Disconnect from all processor connections."""
        for processor_id, connection in self._processor_conns.items():
            _LOGGER.debug("Disconnecting from processor %s", processor_id)
            await connection.stop()

        self._processor_conns.clear()
        _LOGGER.debug("Disconnected from all processors")

    # Event handling
    async def on_server_event(self, event: Event) -> None:
        """Called when an event is received from server."""

        # Explicit handler for Describe/Info flow
        if Describe.is_type(event.type):
            await self._handle_describe_flow(event)
            return # Describe events are not propagated to processors
                
        if not AudioChunk.is_type(event.type):
            # Log all events except AudioChunk to avoid excessive logging
            _LOGGER.debug("Event received from server: %s", event.type)

        # Check for pre_target blocking subscribers
        key = (SubscriptionEvent(event.type), SubscriptionStage.PRE_TARGET, SubscriptionMode.BLOCKING)
        subs = self._subscriptions.get(key, [])

        if subs:
            _LOGGER.debug("Notify all pre-target blocking subscribers (%d) for event %s", len(subs), event.type)
            await self._start_blocking_flow(SubscriptionStage.PRE_TARGET, event, subs)
        else:
            # No blocking subscriptions - send directly to target and non-blocking subscribers
            await self._send_to_target(event)
    
    async def _handle_describe_flow(self, event: Event) -> None:
        try:
            async with AsyncClient.from_uri(self.settings.target.uri) as client:
                await client.connect()
                _LOGGER.debug("Sending '%s' event to target.", event.type)
                await client.write_event(event)

                while True:
                    received_event = await client.read_event()
                    if received_event is None:
                        _LOGGER.debug("Connection lost with target")
                        break
                    
                    _LOGGER.debug("Received '%s' event from target.", received_event.type)

                    if Info.is_type(received_event.type):
                        received_event = enrich_wyoming_info(received_event)
                        target_type = read_service_type(received_event)
                        _LOGGER.debug("Target service type: %s", target_type)
                        if WyomingSttTarget.is_type(target_type):
                            self._target = WyomingSttTarget(
                                uri=self.settings.target.uri,
                                event_callback=self.on_target_event
                            )
                        await self._send_to_server(received_event)
                        break

        except Exception as error:
            _LOGGER.debug("Error processing Describe: %s", error)

    async def on_target_event(self, event: Event) -> None:
        """Called when an event is received from the target service."""

        key = (SubscriptionEvent(event.type), SubscriptionStage.POST_TARGET, SubscriptionMode.BLOCKING)
        subs = self._subscriptions.get(key, [])

        if subs:
            _LOGGER.debug("Notify all post_target blocking subscribers (%d) for event %s", len(subs), event.type)
            await self._start_blocking_flow(SubscriptionStage.POST_TARGET, event, subs)
        else:
            # No blocking subscriptions - send directly to server and non-blocking subscribers
            await self._send_to_server(event)

    async def on_processor_event(self, event: Event) -> None:
        """Called when an event is received from a processor, this event must be part of a blocking flow."""
        _LOGGER.debug("Event received from processor: %s", event.type)

        proc_response = ProcessorResponse.from_event(event)

        tracking_id = proc_response.tracking_id
        if not tracking_id:
            _LOGGER.warning("Missing tracking_id in processor response, ignoring event: %s", event.type)
            return

        processor_id = proc_response.processor_id
        if not processor_id:
            _LOGGER.warning("Missing processor_id in processor response, tracking_id: %s", tracking_id)
            return

        tracker = self._processor_trackers.get(tracking_id)
        if not tracker:
            _LOGGER.warning("Processor '%s' not being tracked, tracking_id: %s", processor_id, tracking_id)
            return
        
        if tracker.is_complete():
            _LOGGER.debug("Processor '%s' responded after completion, tracking_id: %s", processor_id, tracking_id)
            return
        
        tracker.finalize_processor(processor_id, proc_response.ext)

        _LOGGER.debug("Received processor response from %s. Pending: %d/%d", processor_id, len(tracker.pending_processors), len(tracker.processor_extensions))

        # Check if all processors have responded
        if tracker.is_complete():
            await self._end_blocking_flow(tracking_id, tracker)

    async def _start_blocking_flow(self, stage: SubscriptionStage, event: Event, subs: List[ProcessorSubscription]) -> None:
        tracker = ProcessorTracker(event, stage)
        tracking_id = tracker.tracking_id
        
        # Send to all blocking subscribers
        for sub in subs:
            proc_conn = self._processor_conns.get(sub.processor_id)
            if not proc_conn:
                _LOGGER.warning("Processor connection not found by id '%s'", sub.processor_id)
                continue

            trackable_event = self._attach_tracking_info(event, tracking_id, sub.processor_id)
            
            # Register this subscription as pending
            tracker.track_processor(sub.processor_id)
            
            _LOGGER.debug("Sending event to blocking subscription '%s' with tracking_id '%s'", sub.processor_id, tracking_id)
            
            try:
                await proc_conn.send_event(trackable_event)
            except Exception:
                _LOGGER.exception("Failed to send event to blocking subscription '%s'", sub.processor_id)
                # Remove from pending since it failed
                tracker.remove_failed_processor(sub.processor_id)
                
        
        # Store the tracker
        self._processor_trackers[tracking_id] = tracker
        
        if tracker.is_complete():
            _LOGGER.debug("No blocking subscribers available, finalizing event immediately")
            await self._end_blocking_flow(tracking_id, tracker, stage)

    async def _end_blocking_flow(self, tracking_id: TrackingId, tracker: ProcessorTracker, stage: SubscriptionStage) -> None:
        """Complete processor flow by merging responses and finalizing event."""
        _LOGGER.debug("Completing processor flow for tracking_id: %s with %d response(s)", tracking_id, len(tracker.processor_extensions))

        # Finalize the enriched event based on stage
        if stage == SubscriptionStage.PRE_TARGET:
            # To target
            enriched_event = tracker.get_processed_event()
            await self._send_to_target(enriched_event)
        else:
            # To server
            self._update_all_input_text(tracker.get_extensions())
            await self._send_to_server(tracker.original_event)
        
        # Clean up tracker
        del self._processor_trackers[tracking_id]

    async def _handle_non_blocking_flow(self, stage: SubscriptionStage, event: Event) -> None:
        # Search for non-blocking post-target subscribers
        key = (SubscriptionEvent(event.type), stage, SubscriptionMode.NON_BLOCKING)
        subs = self._subscriptions.get(key, [])

        if subs:
            _LOGGER.debug("Notifying %d %s non-blocking processors for event %s", len(subs), stage, event.type)
            # Create tasks to send event to all observer processors
            tasks = []
            for proc_sub in subs:
                processor_conn = self._processor_conns.get(proc_sub.processor_id)
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
    
    async def _send_to_target(self, sent_event: Event) -> None:
        """Send server event to target and pre-target non-blocking subscribers."""

        if not self._target:
            _LOGGER.debug("Target connection not found, cannot send event: %s", sent_event.type)
            return
        
        await self._target.write_event(sent_event)
        await self._handle_non_blocking_flow(SubscriptionStage.PRE_TARGET, sent_event)
    
    async def _send_to_server(self, event: Event) -> None:
        """Send final event to server and post-target non-blocking subscribers."""
        
        _LOGGER.debug("Sending event to server: %s", event.type)
        await self._server.send_event(event)
        await self._handle_non_blocking_flow(SubscriptionStage.POST_TARGET, event)
    

    def _attach_tracking_info(self, event: Event, tracking_id: TrackingId, processor_id: ProcessorId) -> Event:
        """Clone the event with correlation ID and processor ID data."""

        # Clone the event's data adding tracking_id and processor_id
        event_data = event.data.copy() if event.data else {}
        event_data["tracking_id"] = TrackingId(tracking_id)
        event_data["processor_id"] = ProcessorId(processor_id)
        
        # Create new event with updated data
        new_event = Event.from_dict({
            "type": event.type,
            "data": event_data
        })

        if event.payload:
            new_event.payload = event.payload

        return new_event

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

    def _update_all_input_text(self, fields: ProcessorExtensions) -> None:
        """Update Home Assistant input_text entities with processor extensions."""
        for key, value in fields.items():
            self._update_input_text(key, value)