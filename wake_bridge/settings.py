from abc import ABC
from dataclasses import dataclass, field
from typing import List, Optional

from wyoming.info import Info


@dataclass(frozen=True)
class ServiceSettings(ABC):
    """Base class for service settings."""

    uri: Optional[str] = None
    """tcp://ip-address:port"""

    command: Optional[List[str]] = None
    """program + args"""

    reconnect_seconds: float = 3.0
    """Seconds before reconnection attempt is made."""

    @property
    def enabled(self) -> bool:
        """True if service is enabled."""
        return bool(self.uri or self.command)


@dataclass(frozen=True)
class WakeWordAndPipeline:
    """Wake word name + optional pipeline name."""

    name: str
    pipeline: Optional[str] = None


@dataclass(frozen=True)
class TargetSettings(ServiceSettings):
    """Wake word service settings."""

    names: Optional[List[WakeWordAndPipeline]] = None
    """List of wake word names to listen for."""

    rate: int = 16000
    """Sample rate of wake word audio (hertz)"""

    width: int = 2
    """Sample width of wake word audio (bytes)"""

    channels: int = 1
    """Sample channels in wake word audio"""

    refractory_seconds: Optional[float] = 5.0
    """Seconds after a wake word detection before another detection is handled."""


@dataclass(frozen=True)
class BridgeSettings:
    """Wyoming bridge settings."""

    target: TargetSettings = field(default_factory=TargetSettings)
    restart_timeout: float = 5.0
    wyoming_info: Optional[Info] = None
