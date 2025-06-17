#!/usr/bin/env python3
import argparse
import asyncio
import logging
import signal
from functools import partial

from wyoming.server import AsyncServer

from wyoming_bridge.core.bridge import WyomingBridge
from wyoming_bridge.events.handler import WyomingEventHandler
from wyoming_bridge.integrations.homeassistant import Homeassistant
from wyoming_bridge.logging import configure_loggers
from wyoming_bridge.processors.config import get_processors

from . import __version__

_LOGGER = logging.getLogger("main")

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", help="unix:// or tcp://", default="tcp://0.0.0.0:11000")
    parser.add_argument("--target-uri", help="URI of Wyoming target service")
    parser.add_argument("--hass-access-token", help="Access token for Home Assistant")
    parser.add_argument("--hass-url", help="Home Assistant URL", default="http://homeassistant:8123")
    parser.add_argument("--processors-path", help="Path to the processors configuration file", default="processors.yml")
    parser.add_argument("--log-level", dest="log_level_default", default=None, help="Default log level (e.g. INFO, DEBUG)")
    parser.add_argument("--log-level-main", dest="log_level_main", default=None, help="Log level for main group (main, processors, handler)")
    parser.add_argument("--log-level-bridge", dest="log_level_bridge", default=None, help="Log level for bridge group")
    parser.add_argument("--log-level-conns", dest="log_level_conns", default=None, help="Log level for connections group")
    return parser.parse_args()

async def main() -> None:
    """Main function to run the Wyoming Bridge."""
    args = parse_arguments()

    configure_loggers(args)
    _LOGGER.info("Starting Wyoming Bridge version %s", __version__)
    _LOGGER.debug(args)

    processors = get_processors(args.processors_path)
    hass = Homeassistant(
        access_token=args.hass_access_token or "",
        url=args.hass_url or "",
    )

    wyoming_bridge = WyomingBridge(target_uri=args.target_uri, processors=processors, hass=hass)
    wyoming_bridge_task = asyncio.create_task(wyoming_bridge.run(), name="wyoming bridge")

    wyoming_server = AsyncServer.from_uri(args.uri)

    try:
        await wyoming_server.run(partial(WyomingEventHandler, wyoming_bridge))
    except KeyboardInterrupt:
        pass
    finally:
        await wyoming_bridge.stop()
        await wyoming_bridge_task


def handle_stop_signal(*args):
    """Handle shutdown signal."""
    _LOGGER.info("Received stop signal. Shutting down...")
    loop = asyncio.get_event_loop()
    loop.stop()


if __name__ == "__main__":
    # Set up signal handling for graceful shutdown
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    asyncio.run(main())
