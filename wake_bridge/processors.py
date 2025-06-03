import logging
import os

import yaml
import json
import jsonschema

# Typing imports
from typing import List, TypedDict, Literal, Optional, cast

_LOGGER = logging.getLogger()


class SubscriptionEnricher(TypedDict, total=False):
    event: str
    from_: Literal["source", "target"]
    role: Literal["enricher"]
    depends_on: List[str]


class SubscriptionObserver(TypedDict):
    event: str
    from_: Literal["source", "target"]
    role: Literal["observer"]
    # 'depends_on' not allowed


Subscription = SubscriptionObserver | SubscriptionEnricher


class Processor(TypedDict):
    id: str
    uri: str
    subscriptions: List[Subscription]


Processors = List[Processor]


def validate_processors_config(processors, schema_path: str):
    """Validate processors config against the JSON schema."""
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


def load_processors_config(processors_path: str):
    """Load processors configuration from a YAML file."""
    try:
        with open(processors_path, "r") as processors_file:
            processors = yaml.safe_load(processors_file)
            _LOGGER.debug("Processors configuration loaded successfully.")
            return processors
    except FileNotFoundError:
        _LOGGER.error(
            f"Processors configuration file not found: {processors_path}")
        raise
    except yaml.YAMLError as e:
        _LOGGER.error(f"Error parsing processors configuration: {e}")
        raise


def config_to_processor(processors_config: list) -> Processors:
    """Recursively convert 'processor configs' to 'Processor'."""
    result = []
    for proc in processors_config:
        new_proc = dict(proc)
        new_subs = []
        for sub in proc["subscriptions"]:
            new_sub = dict(sub)
            if "from" in new_sub:
                new_sub["from_"] = new_sub.pop("from")
            new_subs.append(new_sub)
        new_proc["subscriptions"] = new_subs
        result.append(new_proc)
    return cast(Processors, result)


def get_processors(processors_path: str) -> Processors:
    """Get processors configuration after validation, with full typing."""
    processors_config = load_processors_config(processors_path)
    schema_path = os.path.join(os.path.dirname(__file__), "processors.json")
    validate_processors_config(processors_config, schema_path)
    return config_to_processor(processors_config)
