import asyncio
import logging
from typing import Optional, Dict, Tuple

from wyoming.audio import AudioChunk
from wyoming.client import AsyncClient
from wyoming.event import Event
from wyoming.info import Describe, Info

from wyoming_bridge.connections.processor import ProcessorConnection
from wyoming_bridge.connections.stt import WyomingSttConnection
from wyoming_bridge.connections.target import WyomingTargetConnection
from wyoming_bridge.connections.server import ServerConnection
from wyoming_bridge.core.info import wrap_wyoming_info, read_service_type
from wyoming_bridge.integrations.homeassistant import Homeassistant
from wyoming_bridge.processors.types import Processors, ProcessorId, SubscriptionMode, SubscriptionStage
from wyoming_bridge.events.pipeline import Pipeline, ProcessorEntry, Subscriptions

_LOGGER = logging.getLogger("bridge")

class WyomingBridge:
    def __init__(self, target_uri: str, processors: Processors, hass: Homeassistant) -> None:
        _LOGGER.debug("Initializing WyomingBridge.")
        self._target_uri = target_uri
        self._processors = processors
        self._hass = hass
        self._running = False

        self._server = ServerConnection()
        self._target: Optional[WyomingTargetConnection] = None

        self._subscriptions: Dict[Tuple[SubscriptionStage, SubscriptionMode], Subscriptions] = {}
        self._build_subscriptions_index()
        
        self._downstream: Optional[Pipeline] = None
        self._upstream: Optional[Pipeline] = None

    @property
    def event_handler_id(self) -> Optional[str]:
        return self._server.event_handler_id

    def _build_subscriptions_index(self) -> None:
        self._subscriptions.clear()

        for processor in self._processors:
            for sub in processor["subscriptions"]:

                key = (sub["stage"], sub["mode"])

                if key not in self._subscriptions:
                    self._subscriptions[key] = {}
                
                if sub["event"] not in self._subscriptions[key]:
                    self._subscriptions[key][sub["event"]] = []

                entry = ProcessorEntry(
                    processor_id=ProcessorId(processor["id"]),
                    connection=ProcessorConnection(
                        uri=processor["uri"],
                        processor_id=ProcessorId(processor["id"]),
                    )
                )
                self._subscriptions[key][sub["event"]].append(entry)

    def _build_event_flows(self) -> None:
        if not self._target:
            _LOGGER.warning("No target connection available.")
            self._downstream = None
            return
        
        if not self._server:
            _LOGGER.warning("No server connection available.")
            self._upstream = None
            return

        self._downstream = Pipeline(
            destination=self._target,
            blocking_subscriptions=self._subscriptions.get((SubscriptionStage.PRE_TARGET, SubscriptionMode.BLOCKING), {}),
            non_blocking_subscriptions=self._subscriptions.get((SubscriptionStage.PRE_TARGET, SubscriptionMode.NON_BLOCKING), {}),
            on_blocking_flow_complete=self._hass.store_extensions
        )

        self._upstream = Pipeline(
            destination=self._server,
            blocking_subscriptions=self._subscriptions.get((SubscriptionStage.POST_TARGET, SubscriptionMode.BLOCKING), {}),
            non_blocking_subscriptions=self._subscriptions.get((SubscriptionStage.POST_TARGET, SubscriptionMode.NON_BLOCKING), {}),
            on_blocking_flow_complete=self._hass.store_extensions
        )

    async def start(self) -> None:
        if self._running:
            return
        
        self._running = True
        _LOGGER.info("Wyoming bridge started successfully")

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        # Signal the run loop to stop
        if hasattr(self, '_stop_event'):
            self._stop_event.set()

        await self._server.unbind_event_handler()
        _LOGGER.info("Wyoming bridge stopped")

    async def run(self) -> None:
        """Run main bridge loop."""
        await self.start()
        
        try:
            # Wait for stop signal - all work is event-driven
            self._stop_event = asyncio.Event()
            await self._stop_event.wait()
        except asyncio.CancelledError:
            _LOGGER.info("Bridge loop cancelled")
            raise
        finally:
            await self.stop()

    # Server bindings
    async def bind_server_handler(self, event_handler_id: str, writer: asyncio.StreamWriter) -> None:
        """Set current server event writer."""
        await self._server.bind_event_handler(event_handler_id, writer)

    async def unbind_server_handler(self) -> None:
        """Remove server event writer."""
        await self._server.unbind_event_handler()

    # Event handling
    async def on_server_event(self, event: Event) -> None:
        # Explicitly handle the Describe/Info flow
        if Describe.is_type(event.type):
            await self._handle_describe_flow(event)
            # Describe events are not propagated to processors
            return
                
        if not AudioChunk.is_type(event.type):
            # Log all events except AudioChunk to avoid excessive logging
            _LOGGER.debug("Event received from server: %s", event.type)

        if not self._downstream:
            _LOGGER.warning("No downstream flow found.")
            return
        
        await self._downstream.process_event(event)
    
    async def on_target_event(self, event: Event) -> None:
        if not self._upstream:
            _LOGGER.warning("No server connection available for event: %s", event.type)
            return
        
        await self._upstream.process_event(event)

    async def _handle_describe_flow(self, event: Event) -> None:
        try:
            async with AsyncClient.from_uri(self._target_uri) as client:
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
                        received_event = wrap_wyoming_info(received_event)
                        target_type = read_service_type(received_event)
                        _LOGGER.debug("Target service type: %s", target_type)
                        if WyomingSttConnection.is_type(target_type):
                            self._target = WyomingSttConnection(
                                uri=self._target_uri,
                                on_target_event=self.on_target_event
                            )
                            self._build_event_flows()
                        await self._server.write_event(received_event)
                        break

        except ConnectionError as error:
            _LOGGER.error("Failed to connect to target: %s", error)
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout connecting to target")
        except Exception:
            _LOGGER.exception("Unexpected error processing Describe")
