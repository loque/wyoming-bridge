import logging
import os

import yaml
import json
import jsonschema

from typing import List, TypedDict, Literal, cast, NewType

_LOGGER = logging.getLogger(__name__)

ProcessorId = NewType('ProcessorId', str)
SubscriptionEvent = NewType('SubscriptionEvent', str)

class SubscriptionEnricher(TypedDict, total=False):
    event: SubscriptionEvent
    origin: Literal["source", "target"]
    role: Literal["enricher"]
    depends_on: List[ProcessorId]


class SubscriptionObserver(TypedDict):
    event: SubscriptionEvent
    origin: Literal["source", "target"]
    role: Literal["observer"]
    # 'depends_on' not allowed


Subscription = SubscriptionObserver | SubscriptionEnricher

class Processor(TypedDict):
    id: ProcessorId
    uri: str
    subscriptions: List[Subscription]


Processors = List[Processor]

def validate_processors_config(processors: Processors) -> None:
    """Validate processors config."""

    # Validate the processors configuration against a JSON schema.
    schema_path = os.path.join(os.path.dirname(__file__), "processors.json")
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

    # Check for unique processor IDs
    ids = [proc.get("id") for proc in processors]
    if len(ids) != len(set(ids)):
        duplicates = set([x for x in ids if ids.count(x) > 1])
        _LOGGER.error(
            f"Duplicate processor IDs found: {', '.join(duplicates)}")
        raise ValueError(
            f"Duplicate processor IDs found: {', '.join(duplicates)}")

    # Create a set of all processor IDs for quick lookups
    processor_ids = set(ids)

    # Check depends_on references
    for proc in processors:
        proc_id = proc.get("id")
        for subscription in proc.get("subscriptions", []):
            if "role" in subscription and subscription["role"] == "enricher" and "depends_on" in subscription:
                depends_on_list = subscription["depends_on"]

                # Check if processor references itself
                if proc_id in depends_on_list:
                    _LOGGER.error(
                        f"Processor '{proc_id}' depends on itself, which is not allowed")
                    raise ValueError(
                        f"Processor '{proc_id}' cannot depend on itself")

                # Check if all referenced IDs exist
                for dep_id in depends_on_list:
                    if dep_id not in processor_ids:
                        _LOGGER.error(
                            f"Processor '{proc_id}' depends on non-existent processor '{dep_id}'")
                        raise ValueError(
                            f"Processor '{proc_id}' depends on non-existent processor '{dep_id}'")

    # For now, we won't check for circular dependencies because this
    # implementation might result in false positives for complex valid
    # configurations.
    #
    # # Check for circular dependencies
    # def check_circular_dependencies(proc_id, visited=None, path=None): if
    #     visited is None: visited = set() if path is None: path = []

    #     if proc_id in path:
    #         cycle = path[path.index(proc_id):] + [proc_id]
    #         _LOGGER.error(
    #             f"Circular dependency detected: {' -> '.join(cycle)}")
    #         raise ValueError(
    #             f"Circular dependency detected: {' -> '.join(cycle)}")

    #     if proc_id in visited:
    #         return

    #     visited.add(proc_id)
    #     path.append(proc_id)

    #     # Find the processor by ID
    #     processor = next(
    #         (p for p in processors if p.get("id") == proc_id), None)
    #     if processor:
    #         for subscription in processor.get("subscriptions", []):
    #             if "role" in subscription and subscription["role"] == "enricher" and "depends_on" in subscription:
    #                 for dep_id in subscription["depends_on"]:
    #                     check_circular_dependencies(
    #                         dep_id, visited, path.copy())

    # # Run circular dependency check for each processor
    # for proc_id in processor_ids:
    #     check_circular_dependencies(proc_id)


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
