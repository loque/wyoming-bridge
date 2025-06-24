import pytest
from unittest.mock import AsyncMock

from wyoming.event import Event
from wyoming.tts import Synthesize

from wyoming_bridge.connections.tts import WyomingTtsConnection

@pytest.fixture
def tts_connection():
    on_target_event_mock = AsyncMock()
    conn = WyomingTtsConnection(uri="mock://tts", on_target_event=on_target_event_mock)
    # Mock the parent's disconnect method
    conn._disconnect = AsyncMock()
    return conn

# Tests for is_type
def test_is_type_tts():
    assert WyomingTtsConnection.is_type("tts") is True

def test_is_type_not_tts():
    assert WyomingTtsConnection.is_type("asr") is False

def test_is_type_none():
    assert WyomingTtsConnection.is_type(None) is False

def test_is_type_empty():
    assert WyomingTtsConnection.is_type("") is False

# Tests for _on_target_event
@pytest.mark.asyncio
async def test_on_target_event_other(tts_connection):
    conn = tts_connection
    other_event = Event(type="other")

    await conn._on_target_event(other_event)

    conn._disconnect.assert_not_awaited()
