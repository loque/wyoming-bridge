
import argparse
import logging
from dataclasses import dataclass
from typing import Optional

formatter = logging.Formatter("%(levelname)-8s %(name)-7s %(message)s")

VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}

@dataclass
class LoggerArgs:
    log_level_default: str = "INFO"
    log_level_main: Optional[str] = None
    log_level_bridge: Optional[str] = None
    log_level_conns: Optional[str] = None

    def __post_init__(self):
        # Normalize to uppercase and validate
        for field_name in [
            "log_level_default",
            "log_level_main",
            "log_level_bridge",
            "log_level_conns",
        ]:
            value = getattr(self, field_name)
            if value is not None:
                value_up = value.upper()
                if value_up not in VALID_LOG_LEVELS:
                    raise ValueError(f"Invalid log level for {field_name}: {value}")
                setattr(self, field_name, value_up)

def configure_logger(name: str, level: Optional[str] = None):
    """
    Configure a logger with the specified name and level.
    If no level is provided, it defaults to INFO.
    """
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            handler.setFormatter(formatter)
    
    if level:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    else:
        logger.setLevel(logging.INFO)
    
    return logger

def configure_loggers(args: argparse.Namespace):
    """Configure loggers for different groups based on command-line arguments."""
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
        )
    except Exception as e:
        raise ValueError(f"Invalid logger arguments: {e}")

    group_levels = {
        "main": values.log_level_main or values.log_level_default,
        "bridge": values.log_level_bridge or values.log_level_default,
        "conns": values.log_level_conns or values.log_level_default,
    }

    for name, level in group_levels.items():
        configure_logger(name, level)

