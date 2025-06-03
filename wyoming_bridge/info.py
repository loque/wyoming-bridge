from typing import Optional

from wyoming.event import Event
from wyoming.info import Artifact, Attribution, Info, Satellite

from . import __version__

artifact = Artifact(
    # Prefix for the target service name
    name="bridge-to-",
    # Prefix for the target service description
    description="Wyoming Bridge to: ",
    attribution=Attribution(
        name="loque", url="https://github.com/loque/wyoming-bridge"
    ),
    installed=True,
    version=__version__,
)

cache: Optional[Info] = None

def enrich_wyoming_info(event: Event) -> Event:
    """Enrich Wyoming info with target info."""
    global cache

    if cache is not None:
        return cache.event()

    target_info = Info.from_event(event)
    
    # Create a new Info object to avoid mutating the original
    enriched_info = Info()
    
    # Service types to iterate over
    service_types = ['asr', 'tts', 'handle', 'intent', 'wake', 'mic', 'snd']
    
    for service_type in service_types:
        services = getattr(target_info, service_type, [])
        if not services:
            continue
        
        enriched_services = []
        
        for service in services:
            # Create a copy of the service to avoid mutation
            enriched_service = type(service).from_dict(service.to_dict())
            
            # Override artifact properties
            enriched_service.version = artifact.version
            enriched_service.installed = artifact.installed
            enriched_service.attribution = artifact.attribution
            
            # Prepend artifact name and description
            enriched_service.name = artifact.name + (enriched_service.name or "")
            enriched_service.description = (artifact.description or "") + (enriched_service.description or "")
            
            enriched_services.append(enriched_service)
        
        setattr(enriched_info, service_type, enriched_services)
    
    # Handle satellite separately as it's optional and singular
    if target_info.satellite is not None:
        # Create a copy of the satellite to avoid mutation
        enriched_satellite = Satellite.from_dict(target_info.satellite.to_dict())

        # Override artifact properties
        enriched_satellite.version = artifact.version
        enriched_satellite.installed = artifact.installed
        enriched_satellite.attribution = artifact.attribution

        # Prepend artifact name and description
        enriched_satellite.name = artifact.name + (enriched_satellite.name or "")
        enriched_satellite.description = (artifact.description or "") + (enriched_satellite.description or "")

        enriched_info.satellite = enriched_satellite

    cache = enriched_info
    return cache.event()

def reset_cache() -> None:
    """Reset the global cache."""
    global cache
    cache = None