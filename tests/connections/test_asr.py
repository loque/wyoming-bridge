import pytest
from unittest.mock import AsyncMock

from wyoming.event import Event
from wyoming.asr import Transcript

from wyoming_bridge.connections.asr import WyomingAsrConnection

@pytest.fixture
def asr_connection():
    on_target_event_mock = AsyncMock()
    conn = WyomingAsrConnection(uri="mock://asr", on_target_event=on_target_event_mock)
    # Mock the parent's disconnect method
    conn._disconnect = AsyncMock()
    return conn, on_target_event_mock

# Tests for is_type
def test_is_type_asr():
    assert WyomingAsrConnection.is_type("asr") is True

def test_is_type_not_asr():
    assert WyomingAsrConnection.is_type("tts") is False

def test_is_type_none():
    assert WyomingAsrConnection.is_type(None) is False

def test_is_type_empty():
    assert WyomingAsrConnection.is_type("") is False

# Tests for _on_target_event
@pytest.mark.asyncio
async def test_on_target_event_transcript(asr_connection):
    conn, on_target_event_mock = asr_connection
    transcript = Transcript(text="hello world")
    transcript_event = transcript.event()

    await conn._on_target_event(transcript_event)

    conn._disconnect.assert_awaited_once()
    on_target_event_mock.assert_awaited_once_with(transcript_event)

@pytest.mark.asyncio
async def test_on_target_event_other(asr_connection):
    conn, on_target_event_mock = asr_connection
    other_event = Event(type="other")

    await conn._on_target_event(other_event)

    conn._disconnect.assert_not_awaited()
    on_target_event_mock.assert_awaited_once_with(other_event)
