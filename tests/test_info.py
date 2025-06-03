import pytest

from wyoming.info import (
    Info, AsrProgram, AsrModel, TtsProgram, TtsVoice, WakeProgram, WakeModel,
    HandleProgram, IntentProgram, MicProgram, SndProgram, Satellite, Attribution
)
from wyoming.audio import AudioFormat

from wyoming_bridge.info import enrich_wyoming_info, artifact, reset_cache

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the global cache before each test."""
    reset_cache()
    yield
    reset_cache()


@pytest.fixture
def sample_attribution():
    """Sample attribution for test services."""
    return Attribution(name="Test Creator", url="https://example.com")


@pytest.fixture
def sample_asr_info(sample_attribution):
    """Sample ASR service info."""
    model = AsrModel(
        name="test-model",
        attribution=sample_attribution,
        installed=True,
        description="Test ASR model",
        version="1.0",
        languages=["en", "es"]
    )
    program = AsrProgram(
        name="test-asr",
        attribution=sample_attribution,
        installed=True,
        description="Test ASR service",
        version="1.0",
        models=[model]
    )
    return Info(asr=[program])


@pytest.fixture
def sample_tts_info(sample_attribution):
    """Sample TTS service info."""
    voice = TtsVoice(
        name="test-voice",
        attribution=sample_attribution,
        installed=True,
        description="Test voice",
        version="1.0",
        languages=["en"]
    )
    program = TtsProgram(
        name="test-tts",
        attribution=sample_attribution,
        installed=True,
        description="Test TTS service",
        version="1.0",
        voices=[voice]
    )
    return Info(tts=[program])


@pytest.fixture
def sample_wake_info(sample_attribution):
    """Sample wake word service info."""
    model = WakeModel(
        name="test-wake",
        attribution=sample_attribution,
        installed=True,
        description="Test wake model",
        version="1.0",
        languages=["en"],
        phrase="hey test"
    )
    program = WakeProgram(
        name="test-wake-service",
        attribution=sample_attribution,
        installed=True,
        description="Test wake service",
        version="1.0",
        models=[model]
    )
    return Info(wake=[program])


@pytest.fixture
def sample_satellite_info(sample_attribution):
    """Sample satellite info."""
    satellite = Satellite(
        name="test-satellite",
        attribution=sample_attribution,
        installed=True,
        description="Test satellite",
        version="1.0",
        area="living room",
        has_vad=True,
        active_wake_words=["hey test"],
        max_active_wake_words=3,
        supports_trigger=True
    )
    return Info(satellite=satellite)


@pytest.fixture
def sample_mic_info(sample_attribution):
    """Sample microphone service info."""
    program = MicProgram(
        name="test-mic",
        attribution=sample_attribution,
        installed=True,
        description="Test microphone",
        version="1.0",
        mic_format=AudioFormat(rate=16000, width=2, channels=1)
    )
    return Info(mic=[program])


def test_enrich_asr_info(sample_asr_info):
    """Test enrichment of ASR service info."""
    event = sample_asr_info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    assert len(enriched_info.asr) == 1
    asr_service = enriched_info.asr[0]
    
    # Check that artifact properties are applied
    assert asr_service.name == "bridge-to-" + "test-asr"
    assert asr_service.description == "Wyoming Bridge to: " + "Test ASR service"
    assert asr_service.version == artifact.version
    assert asr_service.installed == artifact.installed
    assert asr_service.attribution.name == artifact.attribution.name
    assert asr_service.attribution.url == artifact.attribution.url
    
    # Check that models are preserved
    assert len(asr_service.models) == 1
    assert asr_service.models[0].name == "test-model"
    assert asr_service.models[0].description == "Test ASR model"
    assert asr_service.models[0].version == "1.0"
    assert asr_service.models[0].installed is True
    assert asr_service.models[0].attribution.name == sample_asr_info.asr[0].attribution.name
    assert asr_service.models[0].attribution.url == sample_asr_info.asr[0].attribution.url
    assert asr_service.models[0].languages == ["en", "es"]


def test_enrich_tts_info(sample_tts_info):
    """Test enrichment of TTS service info."""
    event = sample_tts_info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    # log enriched_info
    import logging
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.setLevel(logging.DEBUG)
    _LOGGER.debug("Sample TTS Info: %s", event)
    _LOGGER.debug("Enriched TTS Info: %s", enriched_info.tts)

    assert len(enriched_info.tts) == 1
    tts_service = enriched_info.tts[0]
    
    # Check that artifact properties are applied
    assert tts_service.name == "bridge-to-" + "test-tts"
    assert tts_service.description == "Wyoming Bridge to: " + "Test TTS service"
    assert tts_service.attribution.name == artifact.attribution.name
    assert tts_service.attribution.url == artifact.attribution.url
    assert tts_service.version == artifact.version
    assert tts_service.installed == artifact.installed
    assert tts_service.attribution.name == artifact.attribution.name
    
    # Check that voices are preserved
    assert len(tts_service.voices) == 1
    assert tts_service.voices[0].name == "test-voice"
    assert tts_service.voices[0].description == "Test voice"
    assert tts_service.voices[0].version == "1.0"
    assert tts_service.voices[0].installed is True
    assert tts_service.voices[0].attribution.name == sample_tts_info.tts[0].attribution.name
    assert tts_service.voices[0].attribution.url == sample_tts_info.tts[0].attribution.url
    assert tts_service.voices[0].languages == ["en"]


def test_enrich_wake_info(sample_wake_info):
    """Test enrichment of wake word service info."""
    event = sample_wake_info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    assert len(enriched_info.wake) == 1
    wake_service = enriched_info.wake[0]
    
    # Check that artifact properties are applied
    assert wake_service.name == "bridge-to-" + "test-wake-service"
    assert wake_service.description == "Wyoming Bridge to: " + "Test wake service"
    assert wake_service.attribution.name == artifact.attribution.name
    assert wake_service.attribution.url == artifact.attribution.url
    assert wake_service.version == artifact.version
    assert wake_service.installed == artifact.installed
    
    # Check that models are preserved
    assert len(wake_service.models) == 1
    assert wake_service.models[0].name == "test-wake"
    assert wake_service.models[0].description == "Test wake model"
    assert wake_service.models[0].version == "1.0"
    assert wake_service.models[0].installed is True
    assert wake_service.models[0].attribution.name == sample_wake_info.wake[0].attribution.name
    assert wake_service.models[0].attribution.url == sample_wake_info.wake[0].attribution.url
    assert wake_service.models[0].languages == ["en"]
    assert wake_service.models[0].phrase == "hey test"


def test_enrich_satellite_info(sample_satellite_info):
    """Test enrichment of satellite info."""
    event = sample_satellite_info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    assert enriched_info.satellite is not None
    satellite = enriched_info.satellite
    
    # Check that artifact properties are applied
    assert satellite.name == "bridge-to-" + "test-satellite"
    assert satellite.description == "Wyoming Bridge to: " + "Test satellite"
    assert satellite.version == artifact.version
    assert satellite.installed == artifact.installed
    assert satellite.attribution.name == artifact.attribution.name
    assert satellite.attribution.url == artifact.attribution.url
    
    # Check that satellite-specific properties are preserved
    assert satellite.area == "living room"
    assert satellite.has_vad is True
    assert satellite.active_wake_words == ["hey test"]
    assert satellite.max_active_wake_words == 3
    assert satellite.supports_trigger is True


def test_enrich_mic_info(sample_mic_info):
    """Test enrichment of microphone service info."""
    event = sample_mic_info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    assert len(enriched_info.mic) == 1
    mic_service = enriched_info.mic[0]
    
    # Check that artifact properties are applied
    assert mic_service.name == "bridge-to-" + "test-mic"
    assert mic_service.description == "Wyoming Bridge to: " + "Test microphone"
    assert mic_service.version == artifact.version
    assert mic_service.installed == artifact.installed
    assert mic_service.attribution.name == artifact.attribution.name
    assert mic_service.attribution.url == artifact.attribution.url

    # Check that mic format is preserved
    assert mic_service.mic_format.rate == 16000
    assert mic_service.mic_format.width == 2
    assert mic_service.mic_format.channels == 1


def test_enrich_empty_info():
    """Test enrichment of empty info."""
    empty_info = Info()
    event = empty_info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    # All service lists should be empty
    assert len(enriched_info.asr) == 0
    assert len(enriched_info.tts) == 0
    assert len(enriched_info.wake) == 0
    assert len(enriched_info.handle) == 0
    assert len(enriched_info.intent) == 0
    assert len(enriched_info.mic) == 0
    assert len(enriched_info.snd) == 0
    assert enriched_info.satellite is None


def test_enrich_multiple_services(sample_attribution):
    """Test enrichment with multiple services of the same type."""
    model1 = AsrModel(
        name="model1", attribution=sample_attribution, installed=True,
        description="Model 1", version="1.0", languages=["en"]
    )
    model2 = AsrModel(
        name="model2", attribution=sample_attribution, installed=True,
        description="Model 2", version="2.0", languages=["es"]
    )
    program1 = AsrProgram(
        name="asr1", attribution=sample_attribution, installed=True,
        description="ASR 1", version="1.0", models=[model1]
    )
    program2 = AsrProgram(
        name="asr2", attribution=sample_attribution, installed=True,
        description="ASR 2", version="2.0", models=[model2]
    )
    
    info = Info(asr=[program1, program2])
    event = info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    assert len(enriched_info.asr) == 2
    
    # Check both services are enriched
    for i, asr_service in enumerate(enriched_info.asr):
        expected_name = f"bridge-to-asr{i+1}"
        expected_desc = f"Wyoming Bridge to: ASR {i+1}"
        assert asr_service.name == expected_name
        assert asr_service.description == expected_desc
        assert asr_service.version == artifact.version


def test_caching_behavior(sample_asr_info):
    """Test that the function caches results."""
    event = sample_asr_info.event()
    
    # First call should process and cache
    enriched_event1 = enrich_wyoming_info(event)
    
    # Second call should return cached result
    enriched_event2 = enrich_wyoming_info(event)
    
    # Results should be identical
    assert enriched_event1.type == enriched_event2.type
    assert enriched_event1.data == enriched_event2.data
    
    # Reset cache for cleanup
    reset_cache()


def test_handle_none_values(sample_attribution):
    """Test handling of None values in service properties."""
    model = AsrModel(
        name=None,  # Test None name # type: ignore
        attribution=sample_attribution,
        installed=True,
        description=None,  # Test None description
        version="1.0",
        languages=["en"]
    )
    program = AsrProgram(
        name="test-asr",
        attribution=sample_attribution,
        installed=True,
        description="Test service",
        version="1.0",
        models=[model]
    )
    
    info = Info(asr=[program])
    event = info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    asr_service = enriched_info.asr[0]
    
    # Should handle None values gracefully
    assert asr_service.name == "bridge-to-" + "test-asr"
    assert asr_service.description == "Wyoming Bridge to: " + "Test service"


def test_all_service_types(sample_attribution):
    """Test enrichment with all service types present."""
    # Create minimal services for each type
    asr_program = AsrProgram(
        name="asr", attribution=sample_attribution, installed=True,
        description="ASR", version="1.0", models=[]
    )
    tts_program = TtsProgram(
        name="tts", attribution=sample_attribution, installed=True,
        description="TTS", version="1.0", voices=[]
    )
    wake_program = WakeProgram(
        name="wake", attribution=sample_attribution, installed=True,
        description="Wake", version="1.0", models=[]
    )
    handle_program = HandleProgram(
        name="handle", attribution=sample_attribution, installed=True,
        description="Handle", version="1.0", models=[]
    )
    intent_program = IntentProgram(
        name="intent", attribution=sample_attribution, installed=True,
        description="Intent", version="1.0", models=[]
    )
    mic_program = MicProgram(
        name="mic", attribution=sample_attribution, installed=True,
        description="Mic", version="1.0",
        mic_format=AudioFormat(rate=16000, width=2, channels=1)
    )
    snd_program = SndProgram(
        name="snd", attribution=sample_attribution, installed=True,
        description="Snd", version="1.0",
        snd_format=AudioFormat(rate=16000, width=2, channels=1)
    )
    
    info = Info(
        asr=[asr_program],
        tts=[tts_program],
        wake=[wake_program],
        handle=[handle_program],
        intent=[intent_program],
        mic=[mic_program],
        snd=[snd_program]
    )
    
    event = info.event()
    enriched_event = enrich_wyoming_info(event)
    enriched_info = Info.from_event(enriched_event)
    
    # Verify all service types are enriched
    service_types = ['asr', 'tts', 'wake', 'handle', 'intent', 'mic', 'snd']
    for service_type in service_types:
        services = getattr(enriched_info, service_type)
        assert len(services) == 1
        service = services[0]
        assert service.name.startswith("bridge-to-")
        assert service.description.startswith("Wyoming Bridge to: ")
        assert service.version == artifact.version
        assert service.attribution.name == artifact.attribution.name
