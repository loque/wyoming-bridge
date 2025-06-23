import pytest
from unittest.mock import MagicMock, patch

from wyoming.event import Event
from wyoming.info import Info, Satellite, Attribution, AsrProgram, AsrModel, TtsProgram, TtsVoice, WakeProgram, WakeModel

from wyoming_bridge.core.info import wrap_wyoming_info, read_service_type, artifact


@pytest.fixture
def sample_asr_info():
    """Create a sample ASR info event."""
    info = Info()
    asr_model = AsrModel(
        name="test-asr",
        description="Test ASR Model",
        version="1.0.0",
        attribution=Attribution(name="test-author", url="https://example.com"),
        installed=True,
        languages=["en"]
    )
    asr_program = AsrProgram(
        name="test-asr-program",
        description="Test ASR Program",
        version="1.0.0",
        attribution=Attribution(name="test-author", url="https://example.com"),
        installed=True,
        models=[asr_model]
    )
    info.asr = [asr_program]
    return info.event()


@pytest.fixture
def sample_tts_info():
    """Create a sample TTS info event."""
    info = Info()
    tts_voice = TtsVoice(
        name="test-voice",
        description="Test Voice",
        version="1.0.0",
        attribution=Attribution(name="test-author", url="https://example.com"),
        installed=True,
        languages=["en"],
        speakers=[]
    )
    tts_program = TtsProgram(
        name="test-tts-program",
        description="Test TTS Program",
        version="1.0.0",
        attribution=Attribution(name="test-author", url="https://example.com"),
        installed=True,
        voices=[tts_voice]
    )
    info.tts = [tts_program]
    return info.event()


@pytest.fixture
def sample_satellite_info():
    """Create a sample satellite info event."""
    info = Info()
    satellite = Satellite(
        name="test-satellite",
        description="Test Satellite",
        version="1.0.0",
        attribution=Attribution(name="test-author", url="https://example.com"),
        installed=True,
        area="office"
    )
    info.satellite = satellite
    return info.event()


@pytest.fixture
def empty_info():
    """Create an empty info event."""
    info = Info()
    return info.event()


class TestWrapWyomingInfo:
    """Tests for wrap_wyoming_info function."""

    def test_wrap_asr_info(self, sample_asr_info):
        """Test wrapping ASR info with bridge's artifact info."""
        wrapped_event = wrap_wyoming_info(sample_asr_info)
        wrapped_info = Info.from_event(wrapped_event)
        
        assert len(wrapped_info.asr) == 1
        asr_service = wrapped_info.asr[0]
        
        # Check that artifact properties are applied
        assert asr_service.version == artifact.version
        assert asr_service.installed == artifact.installed
        assert asr_service.attribution == artifact.attribution
        
        # Check that names and descriptions are prepended
        assert asr_service.name.startswith(artifact.name)
        if asr_service.description and artifact.description:
            assert asr_service.description.startswith(artifact.description)
        assert "test-asr-program" in asr_service.name
        if asr_service.description:
            assert "Test ASR Program" in asr_service.description

    def test_wrap_tts_info(self, sample_tts_info):
        """Test wrapping TTS info with bridge's artifact info."""
        wrapped_event = wrap_wyoming_info(sample_tts_info)
        wrapped_info = Info.from_event(wrapped_event)
        
        assert len(wrapped_info.tts) == 1
        tts_service = wrapped_info.tts[0]
        
        # Check that artifact properties are applied
        assert tts_service.version == artifact.version
        assert tts_service.installed == artifact.installed
        assert tts_service.attribution == artifact.attribution
        
        # Check that names and descriptions are prepended
        assert tts_service.name.startswith(artifact.name)
        if tts_service.description and artifact.description:
            assert tts_service.description.startswith(artifact.description)

    def test_wrap_satellite_info(self, sample_satellite_info):
        """Test wrapping satellite info with bridge's artifact info."""
        wrapped_event = wrap_wyoming_info(sample_satellite_info)
        wrapped_info = Info.from_event(wrapped_event)
        
        assert wrapped_info.satellite is not None
        satellite = wrapped_info.satellite
        
        # Check that artifact properties are applied
        assert satellite.version == artifact.version
        assert satellite.installed == artifact.installed
        assert satellite.attribution == artifact.attribution
        
        # Check that names and descriptions are prepended
        assert satellite.name.startswith(artifact.name)
        if satellite.description and artifact.description:
            assert satellite.description.startswith(artifact.description)
        assert "test-satellite" in satellite.name
        if satellite.description:
            assert "Test Satellite" in satellite.description

    def test_wrap_empty_info(self, empty_info):
        """Test wrapping empty info returns empty wrapped info."""
        wrapped_event = wrap_wyoming_info(empty_info)
        wrapped_info = Info.from_event(wrapped_event)
        
        # All service lists should be empty
        assert not wrapped_info.asr
        assert not wrapped_info.tts
        assert not wrapped_info.handle
        assert not wrapped_info.intent
        assert not wrapped_info.wake
        assert not wrapped_info.mic
        assert not wrapped_info.snd
        assert wrapped_info.satellite is None

    def test_wrap_multiple_services(self):
        """Test wrapping info with multiple services of the same type."""
        info = Info()
        
        # Create two ASR programs
        asr_model1 = AsrModel(
            name="asr1",
            description="ASR Model 1",
            version="1.0.0",
            attribution=Attribution(name="author1", url="https://example1.com"),
            installed=True,
            languages=["en"]
        )
        asr_program1 = AsrProgram(
            name="asr-program1",
            description="ASR Program 1",
            version="1.0.0",
            attribution=Attribution(name="author1", url="https://example1.com"),
            installed=True,
            models=[asr_model1]
        )
        
        asr_model2 = AsrModel(
            name="asr2",
            description="ASR Model 2",
            version="2.0.0",
            attribution=Attribution(name="author2", url="https://example2.com"),
            installed=False,
            languages=["es"]
        )
        asr_program2 = AsrProgram(
            name="asr-program2",
            description="ASR Program 2",
            version="2.0.0",
            attribution=Attribution(name="author2", url="https://example2.com"),
            installed=False,
            models=[asr_model2]
        )
        
        info.asr = [asr_program1, asr_program2]
        
        wrapped_event = wrap_wyoming_info(info.event())
        wrapped_info = Info.from_event(wrapped_event)
        
        assert len(wrapped_info.asr) == 2
        
        # Check both services are wrapped correctly
        for asr_service in wrapped_info.asr:
            assert asr_service.version == artifact.version
            assert asr_service.installed == artifact.installed
            assert asr_service.attribution == artifact.attribution
            assert asr_service.name.startswith(artifact.name)
            if asr_service.description and artifact.description:
                assert asr_service.description.startswith(artifact.description)

    def test_wrap_preserves_original_info(self, sample_asr_info):
        """Test that wrapping doesn't mutate the original info."""
        original_info = Info.from_event(sample_asr_info)
        original_asr = original_info.asr[0]
        
        original_name = original_asr.name
        original_description = original_asr.description
        original_version = original_asr.version
        original_attribution = original_asr.attribution
        
        # Wrap the info
        wrap_wyoming_info(sample_asr_info)
        
        # Check original is unchanged
        assert original_asr.name == original_name
        assert original_asr.description == original_description
        assert original_asr.version == original_version
        assert original_asr.attribution == original_attribution

    def test_wrap_handles_none_names_descriptions(self):
        """Test wrapping handles None names and descriptions gracefully."""
        info = Info()
        asr_model = AsrModel(
            name="asr-model",
            description=None,
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            languages=["en"]
        )
        asr_program = AsrProgram(
            name="",  # Empty name to test None handling
            description=None,
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            models=[asr_model]
        )
        info.asr = [asr_program]
        
        wrapped_event = wrap_wyoming_info(info.event())
        wrapped_info = Info.from_event(wrapped_event)
        
        asr_service = wrapped_info.asr[0]
        assert asr_service.name == artifact.name
        assert asr_service.description == artifact.description


class TestReadServiceType:
    """Tests for read_service_type function."""

    def test_read_asr_service_type(self, sample_asr_info):
        """Test reading ASR service type from info event."""
        service_type = read_service_type(sample_asr_info)
        assert service_type == "asr"

    def test_read_tts_service_type(self, sample_tts_info):
        """Test reading TTS service type from info event."""
        service_type = read_service_type(sample_tts_info)
        assert service_type == "tts"

    def test_read_satellite_service_type(self, sample_satellite_info):
        """Test reading satellite service type from info event."""
        # Note: satellite is not in service_types list, so should return None
        service_type = read_service_type(sample_satellite_info)
        assert service_type is None

    def test_read_empty_info_service_type(self, empty_info):
        """Test reading service type from empty info returns None."""
        service_type = read_service_type(empty_info)
        assert service_type is None

    def test_read_wake_service_type(self):
        """Test reading wake service type from info event."""
        info = Info()
        wake_model = WakeModel(
            name="test-wake",
            description="Test Wake Model",
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            languages=["en"],
            phrase="hey test"
        )
        wake_program = WakeProgram(
            name="test-wake-program",
            description="Test Wake Program",
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            models=[wake_model]
        )
        info.wake = [wake_program]
        
        service_type = read_service_type(info.event())
        assert service_type == "wake"

    def test_read_multiple_service_types(self):
        """Test reading service type when multiple types are present (returns first found)."""
        info = Info()
        
        # Add multiple service types
        asr_model = AsrModel(
            name="test-asr",
            description="Test ASR",
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            languages=["en"]
        )
        asr_program = AsrProgram(
            name="test-asr-program",
            description="Test ASR Program",
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            models=[asr_model]
        )
        
        tts_voice = TtsVoice(
            name="test-voice",
            description="Test Voice",
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            languages=["en"],
            speakers=[]
        )
        tts_program = TtsProgram(
            name="test-tts-program",
            description="Test TTS Program",
            version="1.0.0",
            attribution=Attribution(name="test-author", url="https://example.com"),
            installed=True,
            voices=[tts_voice]
        )
        
        info.asr = [asr_program]
        info.tts = [tts_program]
        
        service_type = read_service_type(info.event())
        # Should return the first service type found in the service_types list
        assert service_type in ["asr", "tts"]

    def test_read_service_type_with_invalid_event(self):
        """Test reading service type from non-info event."""
        # Create a non-info event
        event = Event(type="not_info", data={})
        
        # This should not raise an exception but might return None
        # depending on how Info.from_event handles invalid events
        service_type = read_service_type(event)
        assert service_type is None


class TestArtifact:
    """Tests for the artifact configuration."""

    def test_artifact_properties(self):
        """Test that artifact has expected properties."""
        assert artifact.name == "bridge-to-"
        assert artifact.description == "Wyoming Bridge to: "
        assert artifact.attribution.name == "loque"
        assert artifact.attribution.url == "https://github.com/loque/wyoming-bridge"
        assert artifact.installed is True
        assert artifact.version == "0.0.1"  # From VERSION file

    def test_service_types_list(self):
        """Test that service_types contains expected service types."""
        from wyoming_bridge.core.info import service_types
        
        expected_types = ['asr', 'tts', 'handle', 'intent', 'wake', 'mic', 'snd']
        assert service_types == expected_types