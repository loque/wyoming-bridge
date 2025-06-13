from dataclasses import dataclass, field
from typing import List

from wyoming_bridge.processors import Processor


@dataclass(frozen=True)
class ServiceSettings():
    """Base class for service settings."""

    uri: str
    """tcp://ip-address:port"""

    reconnect_seconds: float = 3.0
    """Seconds before reconnection attempt is made."""


@dataclass(frozen=True)
class BridgeSettings:
    """Wyoming bridge settings."""

    target: ServiceSettings
    processors: List[Processor] = field(default_factory=list)
    restart_timeout: float = 5.0
    hass_access_token: str = ""
    hass_url: str = ""
