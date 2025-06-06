import logging
import os
import asyncio
from flask import Flask
from flask_cors import CORS
from wyoming.client import AsyncClient

from .handler import handler

async def create_app():
    app = Flask(__name__)
    CORS(app)
    app.logger.setLevel(logging.INFO)

    bridge_uri = os.environ.get("BRIDGE_URI")
    if not bridge_uri:
        raise ValueError("BRIDGE_URI environment variable is not set")

    bridge_client = AsyncClient.from_uri(bridge_uri)

    # Wait for the bridge to be ready
    # Retry for up to 30 seconds, every second
    for _ in range(30):
        try:
            await bridge_client.connect()
            break
        except OSError:
            app.logger.warning(f"Bridge not ready, retrying in 1s")
            await asyncio.sleep(1)
    else:
        raise RuntimeError("Could not connect to bridge after 30 seconds")
    
    app.config['BRIDGE_CLIENT'] = bridge_client

    app.register_blueprint(handler)
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(create_app())
    app.run(host='0.0.0.0', port=port)