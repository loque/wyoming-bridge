from dataclasses import dataclass, field
from typing import List, Optional

from wyoming.info import Info


@dataclass(frozen=True)
class ServiceSettings():
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
class BridgeSettings:
    """Wyoming bridge settings."""

    target: ServiceSettings = field(default_factory=ServiceSettings)
    restart_timeout: float = 5.0
    wyoming_info: Optional[Info] = None
