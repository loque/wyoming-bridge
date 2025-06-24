from wyoming.event import Event

from .target import WyomingTargetConnection

class WyomingWakeConnection(WyomingTargetConnection):
    TARGET_TYPE = "wake"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def is_type(service_type: str | None) -> bool:
        if service_type is None:
            return False
        return service_type == WyomingWakeConnection.TARGET_TYPE
    
    async def _on_target_event(self, event: Event) -> None:
        pass