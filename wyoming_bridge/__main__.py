#!/usr/bin/env python3
import argparse
import asyncio
import logging
import signal
from functools import partial

from wyoming.server import AsyncServer

from wyoming_bridge.bridge import WyomingBridge
from wyoming_bridge.processors import get_processors
from wyoming_bridge.settings import BridgeSettings, ServiceSettings

from .handler import WyomingBridgeEventHandler

from . import __version__

_LOGGER = logging.getLogger()

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", help="unix:// or tcp://",
                        default="tcp://0.0.0.0:11000")

    parser.add_argument(
        "--target-uri", help="URI of Wyoming target service")

    parser.add_argument(
        "--processors-path", help="Path to the processors configuration file", default="processors.yml")

    parser.add_argument("--debug", action="store_true",
                        help="Log DEBUG messages")
    return parser.parse_args()


async def main() -> None:
    """Main function to run the Wyoming Bridge."""
    args = parse_arguments()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

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
    _LOGGER.info("Received stop signal. Shutting down...")
    loop = asyncio.get_event_loop()
    loop.stop()


if __name__ == "__main__":
    # Set up signal handling for graceful shutdown
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    asyncio.run(main())
