import argparse
import asyncio
from functools import partial
import logging

from wyoming.server import AsyncServer

from target.handler import EventHandler

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", help="unix:// or tcp://", default="tcp://0.0.0.0:9001")

    return parser.parse_args()

async def main() -> None:
    """Main function to run the Wyoming Target."""
    args = parse_arguments()

    _LOGGER.info("Starting Wyoming Target with URI: %s", args.uri)

    server = AsyncServer.from_uri(args.uri)

    try:
        await server.run(partial(EventHandler))
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()

if __name__ == "__main__":
    asyncio.run(main())