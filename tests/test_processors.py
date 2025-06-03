import pytest
from unittest.mock import AsyncMock,  patch
from typing import cast

from wyoming.event import Event

from wyoming_bridge.processors import validate_processors_config, Processors
from wyoming_bridge.bridge import WakeBridge, ProcessorId
from wyoming_bridge.settings import BridgeSettings, ServiceSettings


def test_valid_processor_config():
    """Test valid processor configuration."""
    valid_config = cast(Processors, [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source", "role": "observer"}
            ]
        },
        {
            "id": "proc2",
            "uri": "unix:///tmp/proc2.sock",
            "subscriptions": [
                {"event": "transcribe", "origin": "source",
                    "role": "enricher", "depends_on": ["proc3"]}
            ]
        },
        {
            "id": "proc3",
            "uri": "stdio://",
            "subscriptions": [
                {"event": "transcribe", "origin": "target", "role": "enricher"}
            ]
        }
    ])
    # Should not raise any exceptions
    validate_processors_config(valid_config)


def test_duplicate_processor_ids():
    """Test duplicate processor IDs."""
    invalid_config = cast(Processors, [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source", "role": "observer"}]
        },
        {
            "id": "proc1",  # Duplicate ID
            "uri": "tcp://localhost:10002",
            "subscriptions": [
                {"event": "transcribe", "origin": "source", "role": "observer"}]
        }
    ])
    with pytest.raises(ValueError, match="Duplicate processor IDs found:"):
        validate_processors_config(invalid_config)


def test_self_referential_dependency():
    """Test self-referential dependency."""
    invalid_config = cast(Processors, [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source",
                    "role": "enricher", "depends_on": ["proc1"]}
            ]
        }
    ])
    with pytest.raises(ValueError, match="cannot depend on itself"):
        validate_processors_config(invalid_config)


def test_nonexistent_dependency():
    """Test non-existent dependency."""
    invalid_config = cast(Processors, [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source",
                    "role": "enricher", "depends_on": ["proc2"]}
            ]
        }
    ])
    with pytest.raises(ValueError, match="depends on non-existent processor"):
        validate_processors_config(invalid_config)

# For now, we won't check for circular dependencies because this implementation
# might result in false positives for complex valid configurations.
#
# def test_circular_dependency():
#     """Test circular dependency."""
#     invalid_config = [
#         {
#             "id": "proc1",
#             "uri": "tcp://localhost:10001",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc2"]}
#             ]
#         },
#         {
#             "id": "proc2",
#             "uri": "tcp://localhost:10002",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc1"]}
#             ]
#         }
#     ]
#     with pytest.raises(ValueError, match="Circular dependency detected:"):
#         validate_processors_config(invalid_config)


# def test_complex_circular_dependency():
#     """Test complex circular dependency."""
#     invalid_config = [
#         {
#             "id": "proc1",
#             "uri": "tcp://localhost:10001",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc2"]}
#             ]
#         },
#         {
#             "id": "proc2",
#             "uri": "tcp://localhost:10002",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc3"]}
#             ]
#         },
#         {
#             "id": "proc3",
#             "uri": "tcp://localhost:10003",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc1"]}
#             ]
#         }
#     ]
#     with pytest.raises(ValueError, match="Circular dependency detected:"):
#         validate_processors_config(invalid_config)

@pytest.mark.asyncio
async def test_enricher_flow_for_target_events():
    """Test enricher flow for target-originated events."""
    # Create test configuration with enrichers
    processors = cast(Processors, [
        {
            "id": "enricher1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcript", "origin": "target", "role": "enricher"}
            ]
        },
        {
            "id": "enricher2", 
            "uri": "tcp://localhost:10002",
            "subscriptions": [
                {"event": "transcript", "origin": "target", "role": "enricher"}
            ]
        },
        {
            "id": "observer1",
            "uri": "tcp://localhost:10003",
            "subscriptions": [
                {"event": "transcript", "origin": "target", "role": "observer"}
            ]
        }
    ])
    
    # Create bridge settings
    settings = BridgeSettings(
        target=ServiceSettings(uri="tcp://localhost:9999"),
        processors=processors
    )
    
    # Create bridge instance
    bridge = WakeBridge(settings)
    
    # Mock connections
    with patch.object(bridge, '_connect_downstream'), \
         patch.object(bridge, '_disconnect_downstream'):
        
        # Mock processor connections
        mock_enricher1_conn = AsyncMock()
        mock_enricher2_conn = AsyncMock()
        mock_observer1_conn = AsyncMock()
        mock_source_conn = AsyncMock()
        
        bridge._processor_connections = {
            ProcessorId("enricher1"): mock_enricher1_conn,
            ProcessorId("enricher2"): mock_enricher2_conn,
            ProcessorId("observer1"): mock_observer1_conn,
        }
        bridge._source_conn = mock_source_conn
        
        await bridge.start()
        
        # Create original target event
        original_event = Event(
            type="transcript",
            data={"text": "hello world"}
        )
        
        # Process target event - should trigger enricher flow
        await bridge.on_target_event(original_event)
        
        # Verify enrichers were called but source/observers were not yet
        assert mock_enricher1_conn.send_event.called
        assert mock_enricher2_conn.send_event.called
        assert not mock_source_conn.send_event.called
        assert not mock_observer1_conn.send_event.called        # Get the correlation_id from the enricher calls
        enricher1_event = mock_enricher1_conn.send_event.call_args[0][0]
        enricher2_event = mock_enricher2_conn.send_event.call_args[0][0]
        
        # Simulate enricher responses - use the actual correlation IDs sent to enrichers
        enricher1_response = Event(
            type="transcript",
            data={
                "correlation_id": enricher1_event.data["correlation_id"],  # Use actual correlation_id
                "text": "hello world",
                "confidence": 0.95,
                "enricher1_data": "metadata1"
            }
        )
        
        enricher2_response = Event(
            type="transcript", 
            data={
                "correlation_id": enricher2_event.data["correlation_id"],  # Use actual correlation_id
                "text": "hello world",
                "sentiment": "positive",
                "enricher2_data": "metadata2"
            }
        )
        
        # Process enricher responses
        await bridge.on_processor_event(enricher1_response)
        await bridge.on_processor_event(enricher2_response)
        
        # Now source and observers should have been called with enriched event
        assert mock_source_conn.send_event.called
        assert mock_observer1_conn.send_event.called
        
        # Verify the enriched event contains merged data
        final_event = mock_source_conn.send_event.call_args[0][0]
        assert final_event.type == "transcript"
        assert final_event.data["text"] == "hello world"
        assert final_event.data["confidence"] == 0.95
        assert final_event.data["sentiment"] == "positive"
        assert final_event.data["enricher1_data"] == "metadata1"
        assert final_event.data["enricher2_data"] == "metadata2"
        assert "correlation_id" not in final_event.data  # Should be removed from final output
        
        await bridge.stop()


@pytest.mark.asyncio 
async def test_target_event_without_enrichers():
    """Test target event processing when no enrichers are configured."""
    # Create test configuration without enrichers
    processors = cast(Processors, [
        {
            "id": "observer1",
            "uri": "tcp://localhost:10003",
            "subscriptions": [
                {"event": "transcript", "origin": "target", "role": "observer"}
            ]
        }
    ])
    
    # Create bridge settings
    settings = BridgeSettings(
        target=ServiceSettings(uri="tcp://localhost:9999"),
        processors=processors
    )
    
    # Create bridge instance
    bridge = WakeBridge(settings)
    
    # Mock connections
    with patch.object(bridge, '_connect_downstream'), \
         patch.object(bridge, '_disconnect_downstream'):
        
        # Mock processor connections
        mock_observer1_conn = AsyncMock()
        mock_source_conn = AsyncMock()
        
        bridge._processor_connections = {
            ProcessorId("observer1"): mock_observer1_conn,
        }
        bridge._source_conn = mock_source_conn
        
        await bridge.start()
        
        # Create original target event
        original_event = Event(
            type="transcript",
            data={"text": "hello world"}
        )
        
        # Process target event - should go directly to source and observers
        await bridge.on_target_event(original_event)
        
        # Verify source and observer were called immediately
        assert mock_source_conn.send_event.called
        assert mock_observer1_conn.send_event.called
        
        # Verify the event was not modified
        source_event = mock_source_conn.send_event.call_args[0][0]
        assert source_event.type == "transcript"
        assert source_event.data["text"] == "hello world"
        
        await bridge.stop()
