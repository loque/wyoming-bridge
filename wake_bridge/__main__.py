#!/usr/bin/env python3
import argparse
import asyncio
import logging
import signal
from functools import partial

from wyoming.info import Attribution, Info, WakeProgram
from wyoming.server import AsyncServer

from wake_bridge.bridge import WakeBridge
from wake_bridge.settings import BridgeSettings, TargetSettings

from .handler import WakeBridgeEventHandler

from . import __version__

_LOGGER = logging.getLogger()


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="tcp://0.0.0.0:11000",
                        help="unix:// or tcp://")
    parser.add_argument(
        "--wake-uri", help="URI of Wyoming wake word detection service")
    parser.add_argument("--debug", action="store_true",
                        help="Log DEBUG messages")
    return parser.parse_args()


async def main() -> None:
    """Main function to run the Wake Bridge."""
    args = parse_arguments()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    # Initialize base Wyoming info; details from the wake word detection service
    # will be added later
    wyoming_info = Info(
        wake=[
            WakeProgram(
                # Prefix for the wake word detection service name
                name="bridge-to-",
                # Prefix for the wake word detection service description
                description="Wyoming Wake Bridge to: ",
                attribution=Attribution(
                    name="loque", url="https://github.com/loque/wyoming-bridge"
                ),
                installed=True,
                version=__version__,
                # The actual models from the wake word detection service will be added here
                models=[],
            )
        ],
    )

    bridge_settings = BridgeSettings(
        target=TargetSettings(
            uri=args.wake_uri,
            rate=16000,
            width=2,
            channels=1,
            refractory_seconds=5.0,
        ),
        wyoming_info=wyoming_info,
    )

    # Initialize and start WakeBridge
    wake_bridge = WakeBridge(bridge_settings)
    wake_bridge_task = asyncio.create_task(
        wake_bridge.run(), name="wake bridge")

    # Initialize Wyoming server
    wyoming_server = AsyncServer.from_uri(args.uri)

    try:
        await wyoming_server.run(partial(WakeBridgeEventHandler, wake_bridge))
    except KeyboardInterrupt:
        pass
    finally:
        await wake_bridge.stop()
        await wake_bridge_task


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
