import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.audio import AudioChunk

from wyoming_bridge.core.bridge import WyomingBridge
from wyoming_bridge.processors.types import (
    ProcessorId, SubscriptionStage, SubscriptionMode, 
    Processors, SubscriptionEventType
)
from wyoming_bridge.integrations.homeassistant import Homeassistant


def make_event(event_type="test", data=None):
    """Helper function to create events."""
    return Event(type=event_type, data=data or {"foo": "bar"})


def make_processors() -> Processors:
    """Helper function to create test processors."""
    return [
        {
            "id": ProcessorId("processor1"),
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {
                    "event": SubscriptionEventType("audio_chunk"),
                    "stage": SubscriptionStage.PRE_TARGET,
                    "mode": SubscriptionMode.BLOCKING
                },
                {
                    "event": SubscriptionEventType("transcript"),
                    "stage": SubscriptionStage.POST_TARGET,
                    "mode": SubscriptionMode.NON_BLOCKING
                }
            ]
        },
        {
            "id": ProcessorId("processor2"),
            "uri": "tcp://localhost:10002",
            "subscriptions": [
                {
                    "event": SubscriptionEventType("audio_chunk"),
                    "stage": SubscriptionStage.PRE_TARGET,
                    "mode": SubscriptionMode.NON_BLOCKING
                }
            ]
        }
    ]


@pytest.fixture
def mock_hass():
    """Mock Homeassistant integration."""
    hass = MagicMock(spec=Homeassistant)
    hass.store_extensions = AsyncMock()
    return hass


@pytest.fixture
def processors():
    """Test processors fixture."""
    return make_processors()


@pytest.fixture
def bridge(processors, mock_hass):
    """Bridge fixture with mocked dependencies."""
    return WyomingBridge(
        target_uri="tcp://localhost:10000",
        processors=processors,
        hass=mock_hass
    )


class TestWyomingBridgeInit:
    """Test WyomingBridge initialization."""

    def test_init_basic(self, processors, mock_hass):
        """Test basic initialization."""
        bridge = WyomingBridge(
            target_uri="tcp://localhost:10000",
            processors=processors,
            hass=mock_hass
        )
        
        assert bridge._target_uri == "tcp://localhost:10000"
        assert bridge._processors == processors
        assert bridge._hass == mock_hass
        assert not bridge._running
        assert bridge._target is None
        assert bridge._downstream is None
        assert bridge._upstream is None

    def test_init_builds_subscriptions_index(self, processors, mock_hass):
        """Test that initialization builds the subscriptions index correctly."""
        bridge = WyomingBridge(
            target_uri="tcp://localhost:10000",
            processors=processors,
            hass=mock_hass
        )
        
        # Check that subscriptions are indexed correctly
        pre_blocking = bridge._subscriptions.get((SubscriptionStage.PRE_TARGET, SubscriptionMode.BLOCKING), {})
        pre_non_blocking = bridge._subscriptions.get((SubscriptionStage.PRE_TARGET, SubscriptionMode.NON_BLOCKING), {})
        post_non_blocking = bridge._subscriptions.get((SubscriptionStage.POST_TARGET, SubscriptionMode.NON_BLOCKING), {})
        
        # Check audio_chunk blocking subscription
        audio_chunk_event = SubscriptionEventType("audio_chunk")
        transcript_event = SubscriptionEventType("transcript")
        
        assert audio_chunk_event in pre_blocking
        assert len(pre_blocking[audio_chunk_event]) == 1
        assert pre_blocking[audio_chunk_event][0].processor_id == "processor1"
        
        # Check audio_chunk non-blocking subscription
        assert audio_chunk_event in pre_non_blocking
        assert len(pre_non_blocking[audio_chunk_event]) == 1
        assert pre_non_blocking[audio_chunk_event][0].processor_id == "processor2"
        
        # Check transcript subscription
        assert transcript_event in post_non_blocking
        assert len(post_non_blocking[transcript_event]) == 1
        assert post_non_blocking[transcript_event][0].processor_id == "processor1"

    def test_init_empty_processors(self, mock_hass):
        """Test initialization with empty processors list."""
        bridge = WyomingBridge(
            target_uri="tcp://localhost:10000",
            processors=[],
            hass=mock_hass
        )
        
        assert len(bridge._subscriptions) == 0

    def test_event_handler_id_property(self, bridge):
        """Test event_handler_id property delegates to server."""
        bridge._server.event_handler_id = "test_handler"
        assert bridge.event_handler_id == "test_handler"
        
        bridge._server.event_handler_id = None
        assert bridge.event_handler_id is None


class TestSubscriptionsIndex:
    """Test subscription indexing logic."""

    def test_build_subscriptions_index_multiple_same_event(self, mock_hass):
        """Test building index with multiple processors for same event."""
        processors: Processors = [
            {
                "id": ProcessorId("proc1"),
                "uri": "tcp://localhost:10001",
                "subscriptions": [
                    {
                        "event": SubscriptionEventType("audio_chunk"),
                        "stage": SubscriptionStage.PRE_TARGET,
                        "mode": SubscriptionMode.BLOCKING
                    }
                ]
            },
            {
                "id": ProcessorId("proc2"),
                "uri": "tcp://localhost:10002",
                "subscriptions": [
                    {
                        "event": SubscriptionEventType("audio_chunk"),
                        "stage": SubscriptionStage.PRE_TARGET,
                        "mode": SubscriptionMode.BLOCKING
                    }
                ]
            }
        ]
        
        bridge = WyomingBridge(
            target_uri="tcp://localhost:10000",
            processors=processors,
            hass=mock_hass
        )
        
        pre_blocking = bridge._subscriptions.get((SubscriptionStage.PRE_TARGET, SubscriptionMode.BLOCKING), {})
        audio_chunk_event = SubscriptionEventType("audio_chunk")
        assert audio_chunk_event in pre_blocking
        assert len(pre_blocking[audio_chunk_event]) == 2
        
        processor_ids = [entry.processor_id for entry in pre_blocking[audio_chunk_event]]
        assert "proc1" in processor_ids
        assert "proc2" in processor_ids


class TestEventFlows:
    """Test event flow building."""

    @patch('wyoming_bridge.core.bridge.Pipeline')
    def test_build_event_flows_success(self, mock_pipeline_class, bridge):
        """Test successful event flow building."""
        # Mock target
        mock_target = MagicMock()
        bridge._target = mock_target
        
        # Mock pipeline instances
        mock_downstream = MagicMock()
        mock_upstream = MagicMock()
        mock_pipeline_class.side_effect = [mock_downstream, mock_upstream]
        
        bridge._build_event_flows()
        
        # Verify pipelines were created with correct parameters
        assert mock_pipeline_class.call_count == 2
        
        # Check downstream pipeline
        downstream_call = mock_pipeline_class.call_args_list[0]
        assert downstream_call[1]['destination'] == mock_target
        assert 'blocking_subscriptions' in downstream_call[1]
        assert 'non_blocking_subscriptions' in downstream_call[1]
        assert downstream_call[1]['on_blocking_flow_complete'] == bridge._hass.store_extensions
        
        # Check upstream pipeline
        upstream_call = mock_pipeline_class.call_args_list[1]
        assert upstream_call[1]['destination'] == bridge._server
        
        assert bridge._downstream == mock_downstream
        assert bridge._upstream == mock_upstream

    def test_build_event_flows_no_target(self, bridge, caplog):
        """Test event flow building with no target."""
        bridge._target = None
        
        bridge._build_event_flows()
        
        assert bridge._downstream is None
        assert "No target connection available" in caplog.text

    def test_build_event_flows_no_server(self, bridge, caplog):
        """Test event flow building with no server."""
        # Set target so we get to the server check
        bridge._target = MagicMock()
        bridge._server = None
        
        bridge._build_event_flows()
        
        assert bridge._upstream is None
        assert "No server connection available" in caplog.text


class TestLifecycle:
    """Test bridge lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_success(self, bridge):
        """Test successful start."""
        assert not bridge._running
        
        await bridge.start()
        
        assert bridge._running

    @pytest.mark.asyncio
    async def test_start_already_running(self, bridge):
        """Test start when already running."""
        bridge._running = True
        
        await bridge.start()
        
        assert bridge._running

    @pytest.mark.asyncio
    async def test_stop_success(self, bridge):
        """Test successful stop."""
        bridge._running = True
        bridge._server.unbind_event_handler = AsyncMock()
        
        await bridge.stop()
        
        assert not bridge._running
        bridge._server.unbind_event_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_not_running(self, bridge):
        """Test stop when not running."""
        bridge._running = False
        bridge._server.unbind_event_handler = AsyncMock()
        
        await bridge.stop()
        
        assert not bridge._running
        bridge._server.unbind_event_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_with_stop_event(self, bridge):
        """Test stop with existing stop event."""
        bridge._running = True
        bridge._stop_event = MagicMock()
        bridge._stop_event.set = MagicMock()
        bridge._server.unbind_event_handler = AsyncMock()
        
        await bridge.stop()
        
        bridge._stop_event.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_lifecycle(self, bridge):
        """Test complete run lifecycle."""
        bridge.start = AsyncMock()
        bridge.stop = AsyncMock()
        
        # Create a task that cancels quickly
        async def run_and_cancel():
            run_task = asyncio.create_task(bridge.run())
            await asyncio.sleep(0.01)  # Let it start
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass
        
        await run_and_cancel()
        
        bridge.start.assert_called_once()
        bridge.stop.assert_called_once()


class TestServerBinding:
    """Test server binding methods."""

    @pytest.mark.asyncio
    async def test_bind_server_handler(self, bridge):
        """Test binding server handler."""
        mock_writer = MagicMock()
        bridge._server.bind_event_handler = AsyncMock()
        
        await bridge.bind_server_handler("handler123", mock_writer)
        
        bridge._server.bind_event_handler.assert_called_once_with("handler123", mock_writer)

    @pytest.mark.asyncio
    async def test_unbind_server_handler(self, bridge):
        """Test unbinding server handler."""
        bridge._server.unbind_event_handler = AsyncMock()
        
        await bridge.unbind_server_handler()
        
        bridge._server.unbind_event_handler.assert_called_once()


class TestEventHandling:
    """Test event handling methods."""

    @pytest.mark.asyncio
    async def test_on_server_event_describe(self, bridge):
        """Test handling Describe events from server."""
        describe_event = make_event("describe")
        bridge._handle_describe_flow = AsyncMock()
        
        with patch.object(Describe, 'is_type', return_value=True):
            await bridge.on_server_event(describe_event)
        
        bridge._handle_describe_flow.assert_called_once_with(describe_event)

    @pytest.mark.asyncio
    async def test_on_server_event_audio_chunk(self, bridge):
        """Test handling AudioChunk events from server."""
        audio_event = make_event("audio_chunk")
        mock_downstream = AsyncMock()
        bridge._downstream = mock_downstream
        
        with patch.object(Describe, 'is_type', return_value=False), \
             patch.object(AudioChunk, 'is_type', return_value=True):
            await bridge.on_server_event(audio_event)
        
        mock_downstream.process_event.assert_called_once_with(audio_event)

    @pytest.mark.asyncio
    async def test_on_server_event_regular(self, bridge):
        """Test handling regular events from server."""
        regular_event = make_event("transcript")
        mock_downstream = AsyncMock()
        bridge._downstream = mock_downstream
        
        with patch.object(Describe, 'is_type', return_value=False), \
             patch.object(AudioChunk, 'is_type', return_value=False):
            await bridge.on_server_event(regular_event)
        
        mock_downstream.process_event.assert_called_once_with(regular_event)

    @pytest.mark.asyncio
    async def test_on_server_event_no_downstream(self, bridge, caplog):
        """Test handling events with no downstream flow."""
        regular_event = make_event("transcript")
        bridge._downstream = None
        
        with patch.object(Describe, 'is_type', return_value=False):
            await bridge.on_server_event(regular_event)
        
        assert "No downstream flow found" in caplog.text

    @pytest.mark.asyncio
    async def test_on_target_event_success(self, bridge):
        """Test handling events from target."""
        target_event = make_event("transcript")
        mock_upstream = AsyncMock()
        bridge._upstream = mock_upstream
        
        await bridge.on_target_event(target_event)
        
        mock_upstream.process_event.assert_called_once_with(target_event)

    @pytest.mark.asyncio
    async def test_on_target_event_no_upstream(self, bridge, caplog):
        """Test handling target events with no upstream flow."""
        target_event = make_event("transcript")
        bridge._upstream = None
        
        await bridge.on_target_event(target_event)
        
        assert "No server connection available for event: transcript" in caplog.text


class TestDescribeFlow:
    """Test the describe flow handling."""

    @pytest.fixture
    def mock_async_client(self):
        """Fixture for a reusable AsyncClient mock."""
        def _factory(read_event_side_effect=None):
            mock_client = MagicMock()
            mock_client.connect = AsyncMock()
            mock_client.write_event = AsyncMock()
            mock_client.read_event = AsyncMock(side_effect=read_event_side_effect) if read_event_side_effect else AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            return mock_client
        return _factory

    @pytest.mark.asyncio
    async def test_handle_describe_flow_success(self, bridge, mock_async_client):
        """Test successful describe flow."""
        describe_event = make_event("describe")
        info_event = make_event("info")
        wrapped_info_event = make_event("info_wrapped")
        
        # Mock AsyncClient
        mock_client = mock_async_client([info_event, None])
        
        # Mock target connection
        mock_target_class = MagicMock()
        mock_target_instance = MagicMock()
        mock_target_class.return_value = mock_target_instance
        
        bridge._server.write_event = AsyncMock()
        bridge._build_event_flows = MagicMock()
        
        with patch('wyoming.client.AsyncClient.from_uri', return_value=mock_client), \
             patch.object(Info, 'is_type', return_value=True), \
             patch('wyoming_bridge.core.bridge.wrap_wyoming_info', return_value=wrapped_info_event), \
             patch('wyoming_bridge.core.bridge.read_service_type', return_value="asr"), \
             patch('wyoming_bridge.connections.target.WyomingTargetConnection.from_service_type', return_value=mock_target_class):
            
            await bridge._handle_describe_flow(describe_event)
        
        # Verify the flow
        mock_client.connect.assert_called_once()
        mock_client.write_event.assert_called_once_with(describe_event)
        mock_target_class.assert_called_once_with(
            uri=bridge._target_uri,
            on_target_event=bridge.on_target_event
        )
        bridge._build_event_flows.assert_called_once()
        bridge._server.write_event.assert_called_once_with(wrapped_info_event)
        
        assert bridge._target == mock_target_instance

    @pytest.mark.asyncio
    async def test_handle_describe_flow_connection_error(self, bridge, caplog):
        """Test describe flow with connection error."""
        describe_event = make_event("describe")
        
        with patch('wyoming.client.AsyncClient.from_uri') as mock_from_uri:
            mock_from_uri.side_effect = ConnectionError("Connection failed")
            
            await bridge._handle_describe_flow(describe_event)
        
        assert "Failed to connect to target: Connection failed" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_describe_flow_timeout(self, bridge, caplog):
        """Test describe flow with timeout."""
        describe_event = make_event("describe")
        
        with patch('wyoming.client.AsyncClient.from_uri') as mock_from_uri:
            mock_from_uri.side_effect = asyncio.TimeoutError()
            
            await bridge._handle_describe_flow(describe_event)
        
        assert "Timeout connecting to target" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_describe_flow_unexpected_error(self, bridge, caplog):
        """Test describe flow with unexpected error."""
        describe_event = make_event("describe")
        
        with patch('wyoming.client.AsyncClient.from_uri') as mock_from_uri:
            mock_from_uri.side_effect = Exception("Unexpected error")
            
            await bridge._handle_describe_flow(describe_event)
        
        assert "Unexpected error processing Describe" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_describe_flow_no_target_connection(self, bridge, caplog, mock_async_client):
        """Test describe flow when no target connection is found."""
        describe_event = make_event("describe")
        info_event = make_event("info")
        wrapped_info_event = make_event("info_wrapped")
        
        # Mock AsyncClient
        mock_client = mock_async_client([info_event, None])
        
        with patch('wyoming.client.AsyncClient.from_uri', return_value=mock_client), \
             patch.object(Info, 'is_type', return_value=True), \
             patch('wyoming_bridge.core.bridge.wrap_wyoming_info', return_value=wrapped_info_event), \
             patch('wyoming_bridge.core.bridge.read_service_type', return_value="unknown"), \
             patch('wyoming_bridge.connections.target.WyomingTargetConnection.from_service_type', return_value=None):
            
            await bridge._handle_describe_flow(describe_event)
        
        assert "No target connection found for service type 'unknown'" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_describe_flow_connection_lost(self, bridge, mock_async_client):
        """Test describe flow when connection is lost."""
        describe_event = make_event("describe")
        
        # Mock AsyncClient that returns None immediately (connection lost)
        mock_client = mock_async_client([None])
        
        with patch('wyoming.client.AsyncClient.from_uri', return_value=mock_client):
            await bridge._handle_describe_flow(describe_event)
        
        # Should complete without error, just log connection lost
        mock_client.connect.assert_called_once()
        mock_client.write_event.assert_called_once_with(describe_event)