from typing import Optional

from wyoming.event import Event
from wyoming.info import Artifact, Attribution, Info, Satellite

from .. import __version__
from typing import Optional, Literal

artifact = Artifact(
    name="bridge-to-",
    description="Wyoming Bridge to: ",
    attribution=Attribution(
        name="loque", url="https://github.com/loque/wyoming-bridge"
    ),
    installed=True,
    version=__version__,
)

# TODO: use proper type definitions from Wyoming protocol
ServiceType = Literal['asr', 'tts', 'handle', 'intent', 'wake', 'mic', 'snd']
service_types = ['asr', 'tts', 'handle', 'intent', 'wake', 'mic', 'snd']

def wrap_wyoming_info(event: Event) -> Event:
    """Wrap target Info with bridge's info."""

    target_info = Info.from_event(event)
    
    # Create a new Info object to avoid mutating the original
    wrapped_info = Info()
    
    for service_type in service_types:
        services = getattr(target_info, service_type, [])
        if not services:
            continue
        
        wrapped_services = []
        
        for service in services:
            # Create a copy of the service to avoid mutation
            wrapped_service = type(service).from_dict(service.to_dict())
            
            # Override artifact properties
            wrapped_service.version = artifact.version
            wrapped_service.installed = artifact.installed
            wrapped_service.attribution = artifact.attribution
            
            # Prepend artifact name and description
            wrapped_service.name = artifact.name + (wrapped_service.name or "")
            wrapped_service.description = (artifact.description or "") + (wrapped_service.description or "")
            
            wrapped_services.append(wrapped_service)
        
        setattr(wrapped_info, service_type, wrapped_services)
    
    # Handle satellite (optional and singular)
    if target_info.satellite is not None:
        # Create a copy of the satellite to avoid mutation
        wrapped_satellite = Satellite.from_dict(target_info.satellite.to_dict())

        # Override artifact properties
        wrapped_satellite.version = artifact.version
        wrapped_satellite.installed = artifact.installed
        wrapped_satellite.attribution = artifact.attribution

        # Prepend artifact name and description
        wrapped_satellite.name = artifact.name + (wrapped_satellite.name or "")
        wrapped_satellite.description = (artifact.description or "") + (wrapped_satellite.description or "")

        wrapped_info.satellite = wrapped_satellite

    return wrapped_info.event()

def read_service_type(event: Event) -> Optional[ServiceType]:
    """Read the service type from the event."""
    info = Info.from_event(event)

    # Try to infer the service type from event data keys
    for service_type in service_types:
        services = getattr(info, service_type, None)
        if services:  # Check if the service list is not empty
            return service_type  # type: ignore[return-value]

    return None
    