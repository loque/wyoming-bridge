#!/usr/bin/env python3
import argparse
import asyncio
import logging
import signal
import contextlib

from wyoming.info import Attribution, Info, WakeProgram, WakeModel
from wyoming.client import AsyncClient
from wyoming.server import AsyncServer

from .handler import WakeBridgeEventHandler

from . import __version__

_LOGGER = logging.getLogger()

stop_event = asyncio.Event()


def handle_stop_signal(*args):
    """Handle shutdown signal and set the stop event."""
    _LOGGER.info("Received stop signal. Shutting down...")
    stop_event.set()
    exit(0)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="tcp://0.0.0.0:5004",
                        help="unix:// or tcp://")
    parser.add_argument(
        "--wake-uri", help="URI of Wyoming wake word detection service")
    parser.add_argument("--debug", action="store_true",
                        help="Log DEBUG messages")
    return parser.parse_args()


async def main() -> None:
    args = parse_arguments()

    # Set up logging
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    wyoming_info = Info(
        wake=[
            WakeProgram(
                name="bridge-to-",
                description="Wyoming Wake Bridge to: ",
                attribution=Attribution(
                    name="loque", url="https://github.com/loque/wyoming-bridge"
                ),
                installed=True,
                version=__version__,
                models=[],
            )
        ],
    )

    # Connect to Wake service
    wake_client: AsyncClient = AsyncClient.from_uri(args.wake_uri)
    await wake_client.connect()

    # Start server
    server = AsyncServer.from_uri(args.uri)

    # Capture handler instance for shutdown
    handler_container = {}

    def handler_factory(*a, **kw):
        handler = WakeBridgeEventHandler(wyoming_info, wake_client, *a, **kw)
        handler_container['handler'] = handler
        return handler

    try:
        await server.run(handler_factory)
    except KeyboardInterrupt:
        pass
    finally:
        # Graceful shutdown
        _LOGGER.debug("Shutting down")
        handler = handler_container.get('handler')
        if handler is not None:
            await handler.shutdown()
        await wake_client.disconnect()
        await server.stop()


if __name__ == "__main__":
   # Set up signal handling for graceful shutdown
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
