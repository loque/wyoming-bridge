#!/usr/bin/env python3
import argparse
import asyncio
import logging
import signal
from functools import partial

from wyoming.server import AsyncServer

from wyoming_bridge.bridge import WyomingBridge
from wyoming_bridge.loggers import configure_loggers
from wyoming_bridge.processors import get_processors
from wyoming_bridge.settings import BridgeSettings, ServiceSettings


from .handler import WyomingBridgeEventHandler
from . import __version__

_logger = logging.getLogger("main")

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", help="unix:// or tcp://", default="tcp://0.0.0.0:11000")
    parser.add_argument("--target-uri", help="URI of Wyoming target service")
    parser.add_argument("--processors-path", help="Path to the processors configuration file", default="processors.yml")
    parser.add_argument("--log-level", dest="log_level_default", default=None, help="Default log level (e.g. INFO, DEBUG)")
    parser.add_argument("--log-level-main", dest="log_level_main", default=None, help="Log level for main group (main, processors, handler)")
    parser.add_argument("--log-level-bridge", dest="log_level_bridge", default=None, help="Log level for bridge group")
    parser.add_argument("--log-level-conns", dest="log_level_conns", default=None, help="Log level for connections group")
    parser.add_argument("--log-level-state", dest="log_level_state", default=None, help="Log level for state group")
    return parser.parse_args()

async def main() -> None:
    """Main function to run the Wyoming Bridge."""
    args = parse_arguments()

    configure_loggers(args)
    _logger.info("Starting Wyoming Bridge version %s", __version__)
    _logger.debug(args)

    # Validate and load the configured processors
    processors = get_processors(args.processors_path)

    bridge_settings = BridgeSettings(
        target=ServiceSettings(
            uri=args.target_uri,
        ),
        processors=processors,
    )

    # Initialize and start WyomingBridge
    wyoming_bridge = WyomingBridge(bridge_settings)
    wyoming_bridge_task = asyncio.create_task(
        wyoming_bridge.run(), name="wyoming bridge")

    # Initialize Wyoming server
    wyoming_server = AsyncServer.from_uri(args.uri)

    try:
        await wyoming_server.run(partial(WyomingBridgeEventHandler, wyoming_bridge))
    except KeyboardInterrupt:
        pass
    finally:
        await wyoming_bridge.stop()
        await wyoming_bridge_task


def handle_stop_signal(*args):
    """Handle shutdown signal."""
    _logger.info("Received stop signal. Shutting down...")
    loop = asyncio.get_event_loop()
    loop.stop()


if __name__ == "__main__":
    # Set up signal handling for graceful shutdown
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    asyncio.run(main())
