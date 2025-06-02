"""Example of WakeBridge refactored to use the state management abstraction."""

import asyncio
import logging
from typing import Optional

from wyoming.audio import AudioChunk
from wyoming.event import Event
from wyoming.info import Info

from wake_bridge.settings import BridgeSettings
from wake_bridge.connections import DownstreamConnection, UpstreamConnection
from wake_bridge.state_manager import LifecycleManager, BaseState

_LOGGER = logging.getLogger(__name__)


class WakeBridge(LifecycleManager):
    """
    WakeBridge serves as a bridge between the Wake target and the source (e.g.
    Home Assistant).
    """

    def __init__(self, settings: BridgeSettings) -> None:
        """Initializes the WakeBridge with state management."""
        super().__init__("wake_bridge")
        _LOGGER.debug("Initializing WakeBridge with settings: %s", settings)
        self.settings = settings

        # Connection managers
        self._source_conn = UpstreamConnection("source")
        self._target_conn: Optional[DownstreamConnection] = None

        self.wyoming_info: Info = settings.wyoming_info or Info()
        self.wyoming_info_enriched = False

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
        _LOGGER.info("Wake bridge started successfully")

    async def _on_stopping(self) -> None:
        """Handle STOPPING state."""
        await self._disconnect_downstream()
        await self._state_machine.transition_to(BaseState.STOPPED)

    async def _on_stopped(self) -> None:
        """Handle STOPPED state - bridge is fully stopped."""
        _LOGGER.info("Wake bridge stopped")

    async def _on_restarting(self) -> None:
        """Handle RESTARTING state."""
        await self._disconnect_downstream()
        _LOGGER.debug("Restarting bridge in %s second(s)",
                      self.settings.restart_timeout)
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

        _LOGGER.debug("Connecting to target service: %s",
                      self.settings.target.uri)
        self._target_conn = DownstreamConnection(
            name="target",
            uri=self.settings.target.uri,
            reconnect_seconds=self.settings.target.reconnect_seconds,
            event_callback=self.on_target_event
        )
        await self._target_conn.start()

    async def _disconnect_downstream(self) -> None:
        """Disconnects from running services."""
        # Stop target connection
        if self._target_conn is not None:
            await self._target_conn.stop()
            self._target_conn = None

        # Stop source connection manager
        await self._source_conn.stop()

        _LOGGER.debug("Disconnected from services")

    # Event handling
    async def on_source_event(self, event: Event) -> None:
        """Called when an event is received from source."""

        if self._target_conn is None:
            # TODO: improve error handling
            raise RuntimeError("Target connection is not established")

        if not AudioChunk.is_type(event.type):
            _LOGGER.debug("Event received from source: %s", event.type)

        await self._target_conn.send_event(event)

    async def on_target_event(self, event: Event) -> None:
        """Called when an event is received from the target service."""

        if Info.is_type(event.type):
            event = self._enrich_wyoming_info(event)

        # Forward event (enriched or not) to source
        await self._source_conn.send_event(event)

    def _enrich_wyoming_info(self, event: Event) -> Event:
        """Enhance bridge info with target info."""
        if self.wyoming_info_enriched:
            return self.wyoming_info.event()

        target_info = Info.from_event(event)
        bridge = self.wyoming_info.wake[0]
        target = target_info.wake[0]

        bridge.name = (bridge.name or "") + (target.name or "")
        bridge.description = (bridge.description or "") + \
            (target.description or "")

        # Models assignment
        bridge.models = target.models

        self.wyoming_info_enriched = True
        return self.wyoming_info.event()
