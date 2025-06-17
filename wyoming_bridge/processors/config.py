import logging
import os
from typing import cast
import json

import yaml
import jsonschema

from wyoming_bridge.processors.types import Processors, SubscriptionMode, SubscriptionStage

_LOGGER = logging.getLogger("main")

def validate_processors_config(processors: Processors) -> None:
    # Validate the processors configuration against a JSON schema.
    schema_path = os.path.join(os.path.dirname(__file__), "schema.json")
    with open(schema_path, "r") as schema_file:
        # Remove any comments (jsonschema does not support them)
        schema_str = schema_file.read()
        # Remove lines starting with //
        schema_str = '\n'.join(
            line for line in schema_str.splitlines() if not line.strip().startswith('//')
        )
        schema = json.loads(schema_str)

    try:
        jsonschema.validate(instance=processors, schema=schema)
        _LOGGER.info("Processors configuration is valid.")
    except jsonschema.ValidationError as err:
        _LOGGER.error(
            f"Processors configuration validation error: {err.message}")
        raise

    # Set default values for mode if not present
    for proc in processors:
        for subscription in proc.get("subscriptions", []):
            if "mode" not in subscription:
                subscription["mode"] = SubscriptionMode.NON_BLOCKING
            # Ensure stage and mode are instances of the Enum
            # YAML load might produce strings, so we convert them
            if isinstance(subscription.get("stage"), str):
                subscription["stage"] = SubscriptionStage(subscription["stage"])
            if isinstance(subscription.get("mode"), str):
                subscription["mode"] = SubscriptionMode(subscription["mode"])


    # Check for unique processor IDs
    ids = [proc.get("id") for proc in processors]
    if len(ids) != len(set(ids)):
        duplicates = set([x for x in ids if ids.count(x) > 1])
        _LOGGER.error(f"Duplicate processor IDs found: {', '.join(duplicates)}")
        raise ValueError(f"Duplicate processor IDs found: {', '.join(duplicates)}")

def load_processors(processors_config_path: str) -> Processors:
    """Load processors configuration from a YAML file."""
    try:
        with open(processors_config_path, "r") as processors_config_file:
            processors = yaml.safe_load(processors_config_file)
            _LOGGER.debug("Processors configuration loaded successfully.")
            return cast(Processors, processors)
    except FileNotFoundError:
        _LOGGER.warning(f"Processors configuration file not found in {processors_config_path}. No processors will be loaded.")
        return []
    except yaml.YAMLError as e:
        _LOGGER.error(f"Error parsing processors configuration: {e}")
        raise

def get_processors(processors_config_path: str) -> Processors:
    """Get processors configuration after validation, with full typing."""
    processors = load_processors(processors_config_path)
    validate_processors_config(processors)
    return processors
