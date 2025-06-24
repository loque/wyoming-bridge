import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from wyoming_bridge.connections.target import WyomingTargetConnection
from wyoming.event import Event

class DummyTarget(WyomingTargetConnection):
    TARGET_TYPE = "dummy"

    async def _on_target_event(self, event: Event) -> None:
        self._handled_event = event

    @staticmethod
    def is_type(service_type: str | None) -> bool:
        return service_type == "dummy"

def make_event(event_type="test"):
    # Event expects a dict for data
    return Event(type=event_type, data={"foo": "bar"})

@pytest.mark.asyncio
async def test_init_and_connect(monkeypatch):
    on_event = AsyncMock()
    dummy = DummyTarget("dummy://uri", on_event)

    # Patch AsyncClient
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    # read_event returns None immediately to end background task
    mock_client.read_event = AsyncMock(return_value=None)
    mock_client.write_event = AsyncMock()
    monkeypatch.setattr("wyoming.client.AsyncClient.from_uri", lambda uri: mock_client)

    await dummy._connect()
    await asyncio.sleep(0.05)  # Let background task run
    assert not dummy.is_connected()  # Should disconnect after None event
    assert dummy._client is None

@pytest.mark.asyncio
async def test_write_event_triggers_connect(monkeypatch):
    dummy_event = make_event()
    on_event = AsyncMock()
    dummy = DummyTarget("dummy://uri", on_event)

    # Patch AsyncClient
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    # read_event returns None to end background task
    mock_client.read_event = AsyncMock(return_value=None)
    mock_client.write_event = AsyncMock()
    monkeypatch.setattr("wyoming.client.AsyncClient.from_uri", lambda uri: mock_client)

    # Not connected yet, should connect on write
    await dummy.write_event(dummy_event)
    await asyncio.sleep(0.05)
    assert not dummy.is_connected()  # Should disconnect after None event
    mock_client.write_event.assert_awaited_with(dummy_event)

@pytest.mark.asyncio
async def test_listen_to_events(monkeypatch):
    on_event = AsyncMock()
    dummy = DummyTarget("dummy://uri", on_event)

    # Patch AsyncClient
    dummy_event = make_event()
    # Return an event, then None to simulate closed connection
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.read_event = AsyncMock(side_effect=[dummy_event, None])
    mock_client.write_event = AsyncMock()
    monkeypatch.setattr("wyoming.client.AsyncClient.from_uri", lambda uri: mock_client)

    await dummy._connect()
    await asyncio.sleep(0.05)
    assert not dummy.is_connected()  # Should disconnect after None event

@pytest.mark.asyncio
async def test_listen_to_events_on_target_event_callable(monkeypatch):
    """Test that _listen_to_events calls on_target_event when callable and handles non-callable gracefully."""
    dummy_event = make_event()
    
    # Test with callable on_target_event
    on_event = AsyncMock()
    dummy = DummyTarget("dummy://uri", on_event)
    
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    # Return an event, then None to end the loop
    mock_client.read_event = AsyncMock(side_effect=[dummy_event, None])
    mock_client.write_event = AsyncMock()
    monkeypatch.setattr("wyoming.client.AsyncClient.from_uri", lambda uri: mock_client)

    await dummy._connect()
    await asyncio.sleep(0.05)  # Let background task run
    
    # Both _on_target_event (sets _handled_event) and on_target_event should be called
    assert dummy._handled_event == dummy_event
    on_event.assert_awaited_once_with(dummy_event)
    assert not dummy.is_connected()  # Should disconnect after None event

@pytest.mark.asyncio  
async def test_listen_to_events_on_target_event_not_callable(monkeypatch):
    """Test that _listen_to_events handles non-callable on_target_event gracefully."""
    dummy_event = make_event()
    
    # Test with non-callable on_target_event
    dummy = DummyTarget("dummy://uri", "not_callable") # type: ignore
    
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    # Return an event, then None to end the loop
    mock_client.read_event = AsyncMock(side_effect=[dummy_event, None])
    mock_client.write_event = AsyncMock()
    monkeypatch.setattr("wyoming.client.AsyncClient.from_uri", lambda uri: mock_client)

    await dummy._connect()
    await asyncio.sleep(0.05)  # Let background task run
    
    # _on_target_event should still be called, but no error should occur
    assert dummy._handled_event == dummy_event
    assert not dummy.is_connected()  # Should disconnect after None event

@pytest.mark.asyncio
async def test_from_service_type(monkeypatch):
    # Should return DummyTarget for 'dummy' and DummyTarget2 for 'dummy2'
    class DummyTarget2(WyomingTargetConnection):
        TARGET_TYPE = "dummy2"
        async def _on_target_event(self, event: Event) -> None:
            pass
        @staticmethod
        def is_type(service_type: str | None) -> bool:
            return service_type == "dummy2"
    
    # Patch WyomingTargetConnection.from_service_type to use DummyTarget2
    orig = WyomingTargetConnection.from_service_type
    def fake_from_service_type(service_type):
        if service_type == "dummy2":
            return DummyTarget2
        return DummyTarget
    monkeypatch.setattr(WyomingTargetConnection, "from_service_type", staticmethod(fake_from_service_type))
    assert WyomingTargetConnection.from_service_type("dummy") is DummyTarget
    assert WyomingTargetConnection.from_service_type("dummy2") is DummyTarget2
    monkeypatch.setattr(WyomingTargetConnection, "from_service_type", orig)

def test_init_subclass_requires_target_type():
    with pytest.raises(TypeError):
        class NoType(WyomingTargetConnection):
            pass
