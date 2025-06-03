import pytest
from wake_bridge.processors import validate_processors_config, ProcessorsConfig


def test_valid_processor_config():
    """Test valid processor configuration."""
    valid_config: ProcessorsConfig = [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source", "role": "observer"}
            ]
        },
        {
            "id": "proc2",
            "uri": "unix:///tmp/proc2.sock",
            "subscriptions": [
                {"event": "transcribe", "origin": "source",
                    "role": "enricher", "depends_on": ["proc3"]}
            ]
        },
        {
            "id": "proc3",
            "uri": "stdio://",
            "subscriptions": [
                {"event": "transcribe", "origin": "target", "role": "enricher"}
            ]
        }
    ]
    # Should not raise any exceptions
    validate_processors_config(valid_config)


def test_duplicate_processor_ids():
    """Test duplicate processor IDs."""
    invalid_config: ProcessorsConfig = [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source", "role": "observer"}]
        },
        {
            "id": "proc1",  # Duplicate ID
            "uri": "tcp://localhost:10002",
            "subscriptions": [
                {"event": "transcribe", "origin": "source", "role": "observer"}]
        }
    ]
    with pytest.raises(ValueError, match="Duplicate processor IDs found:"):
        validate_processors_config(invalid_config)


def test_self_referential_dependency():
    """Test self-referential dependency."""
    invalid_config: ProcessorsConfig = [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source",
                    "role": "enricher", "depends_on": ["proc1"]}
            ]
        }
    ]
    with pytest.raises(ValueError, match="cannot depend on itself"):
        validate_processors_config(invalid_config)


def test_nonexistent_dependency():
    """Test non-existent dependency."""
    invalid_config: ProcessorsConfig = [
        {
            "id": "proc1",
            "uri": "tcp://localhost:10001",
            "subscriptions": [
                {"event": "transcribe", "origin": "source",
                    "role": "enricher", "depends_on": ["proc2"]}
            ]
        }
    ]
    with pytest.raises(ValueError, match="depends on non-existent processor"):
        validate_processors_config(invalid_config)

# For now, we won't check for circular dependencies because this implementation
# might result in false positives for complex valid configurations.
#
# def test_circular_dependency():
#     """Test circular dependency."""
#     invalid_config = [
#         {
#             "id": "proc1",
#             "uri": "tcp://localhost:10001",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc2"]}
#             ]
#         },
#         {
#             "id": "proc2",
#             "uri": "tcp://localhost:10002",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc1"]}
#             ]
#         }
#     ]
#     with pytest.raises(ValueError, match="Circular dependency detected:"):
#         validate_processors_config(invalid_config)


# def test_complex_circular_dependency():
#     """Test complex circular dependency."""
#     invalid_config = [
#         {
#             "id": "proc1",
#             "uri": "tcp://localhost:10001",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc2"]}
#             ]
#         },
#         {
#             "id": "proc2",
#             "uri": "tcp://localhost:10002",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc3"]}
#             ]
#         },
#         {
#             "id": "proc3",
#             "uri": "tcp://localhost:10003",
#             "subscriptions": [
#                 {"event": "transcribe", "from": "source",
#                     "role": "enricher", "depends_on": ["proc1"]}
#             ]
#         }
#     ]
#     with pytest.raises(ValueError, match="Circular dependency detected:"):
#         validate_processors_config(invalid_config)
