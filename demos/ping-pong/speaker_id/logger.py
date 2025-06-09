import logging
from typing import Optional

formatter = logging.Formatter("%(levelname)-6s %(name)-7s %(message)s")

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