import logging
import os
import asyncio
from urllib.parse import urlparse

from flask import Flask
from flask_cors import CORS

from .handler import handler

async def create_app():
    app = Flask(__name__)
    CORS(app)
    app.logger.setLevel(logging.INFO)

    bridge_uri = os.environ.get("BRIDGE_URI")
    if not bridge_uri:
        raise ValueError("BRIDGE_URI environment variable is not set")
    
    result = urlparse(bridge_uri)
    host = result.hostname
    port = result.port or 80

    app.config['BRIDGE_URI'] = {'host': host, 'port': port}

    app.register_blueprint(handler)
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    loop = asyncio.get_event_loop()
    app = loop.run_until_complete(create_app())
    app.run(host='0.0.0.0', port=port)