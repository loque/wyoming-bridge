import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from wyoming.event import Event

from wyoming_bridge.connections.processor import ProcessorConnection
from wyoming_bridge.processors.types import ProcessorId

@pytest.fixture
def processor_connection():
    return ProcessorConnection(uri="mock://processor", processor_id=ProcessorId("test_processor"))

async def cleanup_listener_task(processor_connection):
    if processor_connection._listen_task:
        processor_connection._listen_task.cancel()
        try:
            await processor_connection._listen_task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_connect(processor_connection):
    # Create a mock client that we can control
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.read_event = AsyncMock(return_value=None)  # Ensure read_event task exits
    
    with patch("wyoming.client.AsyncClient.from_uri", return_value=mock_client):
        await processor_connection._connect()
        assert processor_connection._is_connected
        mock_client.connect.assert_called_once()
        
    await cleanup_listener_task(processor_connection)

@pytest.mark.asyncio
async def test_disconnect(processor_connection):
    # Create a mock client that we can control
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.read_event = AsyncMock(return_value=None)  # Ensure read_event task exits
    
    with patch("wyoming.client.AsyncClient.from_uri", return_value=mock_client):
        await processor_connection._connect()
        await processor_connection._disconnect()
        assert not processor_connection._is_connected
        mock_client.disconnect.assert_called_once()
    await cleanup_listener_task(processor_connection)

@pytest.mark.asyncio
async def test_write_event_without_response(processor_connection):
    # Create a mock client that we can control
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.write_event = AsyncMock()
    mock_client.read_event = AsyncMock(return_value=None)  # Ensure read_event task exits
    
    event = Event(type="test_event")
    with patch("wyoming.client.AsyncClient.from_uri", return_value=mock_client):
        await processor_connection._connect()
        await processor_connection.write_event(event, wait_for_response=False)
        mock_client.write_event.assert_called_once_with(event)
        
    await cleanup_listener_task(processor_connection)

@pytest.mark.asyncio
async def test_write_event_with_response(processor_connection):
    event = Event(type="test_event")
    response_event = Event(type="response_event")
    
    # Create a controlled mock client
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.read_event = AsyncMock(return_value=None)  # Default return to stop background task
    
    with patch("wyoming.client.AsyncClient.from_uri", return_value=mock_client):
        await processor_connection._connect()
        
        # Mock the event handling to simulate a response
        async def mock_write_event_with_request_id(event_to_write):
            # Check for request_id in the event data (which write_event should add)
            assert 'data' in event_to_write.__dict__, "Event should have data attribute"
            assert 'request_id' in event_to_write.data, "Event should have request_id in data"
            request_id = event_to_write.data["request_id"]
            
            # Simulate responding to the request by calling the set_result on the waiting future
            response_event.data = {"request_id": request_id}
            if request_id in processor_connection._pending_responses:
                processor_connection._pending_responses[request_id].set_result(response_event)
            return None
            
        # Track if our mock was called
        mock_was_called = False
        
        # Wrap our function to track calls
        async def tracking_mock(event_to_write):
            nonlocal mock_was_called
            mock_was_called = True
            return await mock_write_event_with_request_id(event_to_write)
        
        # Replace the client's write_event method with our tracking mock
        mock_client.write_event = tracking_mock
        
        # Call the actual write_event method with wait_for_response
        response = await processor_connection.write_event(event, wait_for_response=True, timeout=1.0)
        
        assert response == response_event
        
        assert mock_was_called, "write_event was not called"
        
    await cleanup_listener_task(processor_connection)

@pytest.mark.asyncio
async def test_write_event_timeout(processor_connection):
    event = Event(type="test_event")
    
    # Create a controlled mock client
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.write_event = AsyncMock()
    mock_client.read_event = AsyncMock(return_value=None)  # Default return to stop background task
    
    with patch("wyoming.client.AsyncClient.from_uri", return_value=mock_client):
        await processor_connection._connect()
        response = await processor_connection.write_event(event, wait_for_response=True, timeout=0.1)
        assert response is None
        
    await cleanup_listener_task(processor_connection)

@pytest.mark.asyncio
async def test_connect_disconnect_sequence():
    """Test that multiple connect/disconnect cycles work properly"""
    # Create a fresh instance for this test
    processor_connection = ProcessorConnection(
        uri="mock://processor", 
        processor_id=ProcessorId("test_processor")
    )
    
    # Create a mock client that we can control
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.read_event = AsyncMock(return_value=None)  # This will cause the listen task to exit
    
    # Patch the client creation function to return our mock
    with patch("wyoming.client.AsyncClient.from_uri", return_value=mock_client):
        # First connect/disconnect cycle
        await processor_connection._connect()
        assert processor_connection._is_connected
        
        await processor_connection._disconnect()
        assert not processor_connection._is_connected
        
        # Second connect/disconnect cycle
        await processor_connection._connect()
        assert processor_connection._is_connected
        
        await processor_connection._disconnect()
        assert not processor_connection._is_connected
        
        # Verify connect and disconnect were each called twice
        assert mock_client.connect.call_count == 2
        assert mock_client.disconnect.call_count == 2

    await cleanup_listener_task(processor_connection)
