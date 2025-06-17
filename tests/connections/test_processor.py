import pytest
from unittest.mock import AsyncMock, patch

from wyoming.event import Event

from wyoming_bridge.connections.processor import ProcessorConnection
from wyoming_bridge.processors.types import ProcessorId

@pytest.fixture
def processor_connection():
    return ProcessorConnection(uri="mock://processor", processor_id=ProcessorId("test_processor"))

@pytest.mark.asyncio
async def test_connect(processor_connection):
    with patch("wyoming.client.AsyncClient.from_uri", return_value=AsyncMock()) as mock_client:
        await processor_connection._connect()
        assert processor_connection._is_connected
        mock_client.return_value.connect.assert_called_once()

@pytest.mark.asyncio
async def test_disconnect(processor_connection):
    with patch("wyoming.client.AsyncClient.from_uri", return_value=AsyncMock()) as mock_client:
        await processor_connection._connect()
        await processor_connection.disconnect()
        assert not processor_connection._is_connected
        mock_client.return_value.disconnect.assert_called_once()

@pytest.mark.asyncio
async def test_write_event_without_response(processor_connection):
    event = Event(type="test_event")
    with patch("wyoming.client.AsyncClient.from_uri", return_value=AsyncMock()) as mock_client:
        await processor_connection._connect()
        await processor_connection.write_event(event, wait_for_response=False)
        mock_client.return_value.write_event.assert_called_once_with(event)

@pytest.mark.asyncio
async def test_write_event_with_response(processor_connection):
    event = Event(type="test_event")
    response_event = Event(type="response_event")
    
    with patch("wyoming.client.AsyncClient.from_uri", return_value=AsyncMock()) as mock_client:
        mock_client.return_value.write_event = AsyncMock()
        
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
        mock_client.return_value.write_event = tracking_mock
        
        # Call the actual write_event method with wait_for_response
        response = await processor_connection.write_event(event, wait_for_response=True, timeout=1.0)
        
        assert response == response_event
        
        assert mock_was_called, "write_event was not called"

@pytest.mark.asyncio
async def test_write_event_timeout(processor_connection):
    event = Event(type="test_event")
    with patch("wyoming.client.AsyncClient.from_uri", return_value=AsyncMock()) as mock_client:
        await processor_connection._connect()
        response = await processor_connection.write_event(event, wait_for_response=True, timeout=0.1)
        assert response is None
