
import argparse
import logging
from dataclasses import dataclass, field
from typing import Optional

formatter = logging.Formatter("%(levelname)-6s %(name)-7s %(message)s")

VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}

@dataclass
class LoggerArgs:
    log_level_default: str = "INFO"
    log_level_main: Optional[str] = None
    log_level_bridge: Optional[str] = None
    log_level_conns: Optional[str] = None
    log_level_state: Optional[str] = None

    def __post_init__(self):
        # Normalize to uppercase and validate
        for field_name in [
            "log_level_default",
            "log_level_main",
            "log_level_bridge",
            "log_level_conns",
            "log_level_state",
        ]:
            value = getattr(self, field_name)
            if value is not None:
                value_up = value.upper()
                if value_up not in VALID_LOG_LEVELS:
                    raise ValueError(f"Invalid log level for {field_name}: {value}")
                setattr(self, field_name, value_up)

def configure_loggers(args: argparse.Namespace):
    """
    Configure loggers for different groups based on command-line arguments.
    """
    def get_level(attr, default=None):
        value = getattr(args, attr, None)
        return value if value is not None else default
    
    # Convert argparse.Namespace to LoggerArgs
    try:
        values = LoggerArgs(
            log_level_default=get_level("log_level_default", "INFO"),
            log_level_main=get_level("log_level_main", None),
            log_level_bridge=get_level("log_level_bridge", None),
            log_level_conns=get_level("log_level_conns", None),
            log_level_state=get_level("log_level_state", None),
        )
    except Exception as e:
        raise ValueError(f"Invalid logger arguments: {e}")

    group_levels = {
        "main": values.log_level_main or values.log_level_default,
        "bridge": values.log_level_bridge or values.log_level_default,
        "conns": values.log_level_conns or values.log_level_default,
        "state": values.log_level_state or values.log_level_default,
    }

    loggers = {
        "main": logging.getLogger("main"),
        "bridge": logging.getLogger("bridge"),
        "conns": logging.getLogger("conns"),
        "state": logging.getLogger("state"),
    }

    for name, level in group_levels.items():
        if not level:
            continue
        loggers[name].setLevel(getattr(logging, level, logging.INFO))
        if not loggers[name].handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            loggers[name].addHandler(handler)
        else:
            for handler in loggers[name].handlers:
                handler.setFormatter(formatter)

