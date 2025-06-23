import pytest
import logging
from unittest.mock import AsyncMock
import asyncio

from wyoming.event import Event
from wyoming_bridge.events.pipeline import Pipeline, ProcessorEntry
from wyoming_bridge.processors.types import SubscriptionEventType, ProcessorId


@pytest.mark.asyncio
async def test_process_event_no_subscribers_calls_destination_once():
    dest = AsyncMock()
    pipeline = Pipeline(dest, {}, {}, None)
    event = Event(type="foo", data={"foo": "bar"})
    await pipeline.process_event(event)
    dest.write_event.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_process_event_no_destination_logs_warning(caplog):
    caplog.set_level(logging.WARNING)
    # initialize with a dummy destination and then remove it to test warning
    dummy_dest = AsyncMock()
    pipeline = Pipeline(dummy_dest, {}, {}, None)
    # Override private destination attribute to None for testing without violating type
    object.__setattr__(pipeline, '_destination', None)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    assert "No destination provided for event: foo" in caplog.text


@pytest.mark.asyncio
async def test_blocking_and_non_blocking_flow():
    dest = AsyncMock()
    blocking_conn = AsyncMock()
    non_blocking_conn = AsyncMock()
    # Setup blocking subscriber to return a response with extensions
    response_event = Event(type="foo", data={"ext": {"k": "v"}})
    blocking_conn.write_event.return_value = response_event

    subs_blocking = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), blocking_conn)]}
    subs_non_blocking = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc2"), non_blocking_conn)]}
    on_blocking_complete = AsyncMock()

    pipeline = Pipeline(dest, subs_blocking, subs_non_blocking, on_blocking_complete)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)

    # Blocking subscriber called with wait_for_response
    blocking_conn.write_event.assert_called_once_with(event, wait_for_response=True)
    # Destination received the event
    dest.write_event.assert_called_once_with(event)
    # Non-blocking subscriber called without wait_for_response
    non_blocking_conn.write_event.assert_called_once_with(event)
    # Callback for blocking flow complete invoked with collected extensions
    on_blocking_complete.assert_awaited_once_with({"k": "v"})


@pytest.mark.asyncio
async def test_blocking_flow_no_response_does_not_call_callback():
    dest = AsyncMock()
    blocking_conn = AsyncMock()
    # Setup blocking subscriber to return None
    blocking_conn.write_event.return_value = None
    callback = AsyncMock()

    subs_blocking = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), blocking_conn)]}
    pipeline = Pipeline(dest, subs_blocking, {}, callback)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)

    dest.write_event.assert_called_once_with(event)
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_blocking_flow_with_multiple_subscribers():
    """Test that multiple blocking subscribers run in parallel and extensions are merged."""
    dest = AsyncMock()
    conn1, conn2 = AsyncMock(), AsyncMock()
    
    # Different extensions from each processor
    conn1.write_event.return_value = Event(type="foo", data={"ext": {"key1": "value1"}})
    conn2.write_event.return_value = Event(type="foo", data={"ext": {"key2": "value2"}})
    
    subs = {SubscriptionEventType("foo"): [
        ProcessorEntry(ProcessorId("proc1"), conn1),
        ProcessorEntry(ProcessorId("proc2"), conn2)
    ]}
    callback = AsyncMock()
    
    pipeline = Pipeline(dest, subs, {}, callback)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    # Both connections called
    conn1.write_event.assert_called_once_with(event, wait_for_response=True)
    conn2.write_event.assert_called_once_with(event, wait_for_response=True)
    
    # Extensions merged
    callback.assert_awaited_once_with({"key1": "value1", "key2": "value2"})


@pytest.mark.asyncio
async def test_blocking_subscriber_timeout_handling():
    """Test that timeout errors from blocking subscribers are handled gracefully."""
    dest = AsyncMock()
    conn = AsyncMock()
    conn.write_event.side_effect = asyncio.TimeoutError()
    
    subs = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), conn)]}
    callback = AsyncMock()
    
    pipeline = Pipeline(dest, subs, {}, callback)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    # Event still sent to destination despite timeout
    dest.write_event.assert_called_once_with(event)
    # Callback not called due to no successful responses
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_blocking_subscriber_connection_error():
    """Test handling of connection errors from blocking subscribers."""
    dest = AsyncMock()
    conn = AsyncMock()
    conn.write_event.side_effect = ConnectionError("Connection lost")
    
    subs = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), conn)]}
    
    pipeline = Pipeline(dest, subs, {}, None)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    dest.write_event.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_blocking_subscriber_missing_connection():
    """Test handling when processor entry has None connection."""
    dest = AsyncMock()
    
    subs = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), None)]}  # type: ignore
    
    pipeline = Pipeline(dest, subs, {}, None)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    dest.write_event.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_non_blocking_subscriber_missing_connection(caplog):
    """Test that missing connections for non-blocking subscribers are logged."""
    caplog.set_level(logging.WARNING)
    dest = AsyncMock()
    
    subs = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), None)]}  # type: ignore
    
    pipeline = Pipeline(dest, {}, subs, None)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    assert "Processor connection not found for proc1" in caplog.text


@pytest.mark.asyncio
async def test_destination_write_error_handling(caplog):
    """Test that destination write errors are logged but don't crash."""
    caplog.set_level(logging.ERROR)
    dest = AsyncMock()
    dest.write_event.side_effect = Exception("Destination error")
    
    pipeline = Pipeline(dest, {}, {}, None)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    assert "Failed to send event to destination" in caplog.text


@pytest.mark.asyncio
async def test_blocking_flow_invalid_response_data():
    """Test handling of invalid response data from blocking subscribers."""
    dest = AsyncMock()
    conn = AsyncMock()
    # Response without data attribute
    conn.write_event.return_value = Event(type="foo", data={})  # Empty data instead of None
    
    subs = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), conn)]}
    callback = AsyncMock()
    
    pipeline = Pipeline(dest, subs, {}, callback)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    # Should still work without crashing
    dest.write_event.assert_called_once_with(event)
    # Callback not called when no extensions are collected
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_blocking_flow_response_with_none_data():
    """Test handling of response with None data from blocking subscribers."""
    dest = AsyncMock()
    conn = AsyncMock()
    
    # Create a response event that has data set to None after construction
    response_event = Event(type="foo", data={})
    response_event.data = None  # type: ignore
    conn.write_event.return_value = response_event
    
    subs = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), conn)]}
    callback = AsyncMock()
    
    pipeline = Pipeline(dest, subs, {}, callback)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    # Should still work without crashing
    dest.write_event.assert_called_once_with(event)
    # Callback not called when no extensions are collected due to None data
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_blocking_flow_empty_extensions_no_callback():
    """Test that callback isn't called when no extensions are collected."""
    dest = AsyncMock()
    conn = AsyncMock()
    conn.write_event.return_value = Event(type="foo", data={})  # No ext field
    
    subs = {SubscriptionEventType("foo"): [ProcessorEntry(ProcessorId("proc1"), conn)]}
    callback = AsyncMock()
    
    pipeline = Pipeline(dest, subs, {}, callback)
    event = Event(type="foo", data={})
    await pipeline.process_event(event)
    
    dest.write_event.assert_called_once_with(event)
    callback.assert_not_called()
