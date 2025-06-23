"""Tests for the ServerConnection class."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from wyoming.event import Event

from wyoming_bridge.connections.server import ServerConnection


@pytest.mark.asyncio
async def test_init():
    """Test initialization of ServerConnection."""
    conn = ServerConnection()
    assert conn.event_handler_id is None
    assert conn._writer is None


@pytest.mark.asyncio
async def test_bind_event_handler():
    """Test binding an event handler."""
    conn = ServerConnection()
    writer = MagicMock(spec=asyncio.StreamWriter)
    
    await conn.bind_event_handler("test_handler_id", writer)
    
    assert conn.event_handler_id == "test_handler_id"
    assert conn._writer == writer


@pytest.mark.asyncio
async def test_unbind_event_handler():
    """Test unbinding an event handler."""
    conn = ServerConnection()
    writer = MagicMock(spec=asyncio.StreamWriter)
    
    # First bind a handler
    await conn.bind_event_handler("test_handler_id", writer)
    assert conn.event_handler_id == "test_handler_id"
    
    # Then unbind it
    await conn.unbind_event_handler()
    
    assert conn.event_handler_id is None
    assert conn._writer is None


@pytest.mark.asyncio
async def test_write_event_with_no_writer():
    """Test writing an event with no writer set."""
    conn = ServerConnection()
    event = Event(type="test_event", data={"key": "value"})
    
    # Should not raise any exception
    await conn.write_event(event)
    # No assertion needed as the method simply returns if writer is None


@pytest.mark.asyncio
async def test_write_event_success():
    """Test writing an event successfully."""
    conn = ServerConnection()
    writer = MagicMock(spec=asyncio.StreamWriter)
    event = Event(type="test_event", data={"key": "value"})
    
    await conn.bind_event_handler("test_handler_id", writer)
    
    with patch("wyoming_bridge.connections.server.async_write_event", new_callable=AsyncMock) as mock_write:
        await conn.write_event(event)
        
        # Assert that async_write_event was called with the right arguments
        mock_write.assert_called_once_with(event, writer)


@pytest.mark.asyncio
async def test_write_event_connection_reset():
    """Test writing an event with a ConnectionResetError."""
    conn = ServerConnection()
    writer = MagicMock(spec=asyncio.StreamWriter)
    event = Event(type="test_event", data={"key": "value"})
    
    await conn.bind_event_handler("test_handler_id", writer)
    
    with patch("wyoming_bridge.connections.server.async_write_event", new_callable=AsyncMock) as mock_write:
        mock_write.side_effect = ConnectionResetError("Connection reset")
        
        await conn.write_event(event)
        
        # Assert that the handler was unbound
        assert conn.event_handler_id is None
        assert conn._writer is None


@pytest.mark.asyncio
async def test_write_event_generic_exception():
    """Test writing an event with a generic exception."""
    conn = ServerConnection()
    writer = MagicMock(spec=asyncio.StreamWriter)
    event = Event(type="test_event", data={"key": "value"})
    
    await conn.bind_event_handler("test_handler_id", writer)
    
    with patch("wyoming_bridge.connections.server.async_write_event", new_callable=AsyncMock) as mock_write:
        mock_write.side_effect = Exception("Generic error")
        
        await conn.write_event(event)
        
        # Assert that the handler was unbound
        assert conn.event_handler_id is None
        assert conn._writer is None