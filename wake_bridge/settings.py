from dataclasses import dataclass
from typing import List

from wyoming.info import Info

from wake_bridge.processors import Processor


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
    wyoming_info: Info
    processors: List[Processor] = []
    restart_timeout: float = 5.0
