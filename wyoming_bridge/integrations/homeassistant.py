import logging

import aiohttp

from wyoming_bridge.processors.types import ProcessorExtensions

_LOGGER = logging.getLogger("bridge")

class Homeassistant:
    def __init__(self, url: str, access_token: str):
        self.url = url
        self.access_token = access_token
    
    async def _update_input_text(self, key: str, value: str):
        url = f"{self.url}/api/services/input_text/set_value"
        data = {
            "entity_id": f"input_text.{key}",
            "value": value
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        _LOGGER.debug("Updating input_text '%s' with value: %s. URL: %s, Data: %s, Headers: %s", key, value, url, data, headers)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if not response.ok:
                        error_text = await response.text()
                        _LOGGER.error("Failed to update input_text '%s': %s", key, error_text)
                    else:
                        _LOGGER.debug("input_text '%s' updated successfully", key)
        except Exception as e:
            _LOGGER.exception("Exception while updating input_text '%s': %s", key, e)

    async def store_extensions(self, extensions: ProcessorExtensions) -> None:
        for key, value in extensions.items():
            await self._update_input_text(key, value)