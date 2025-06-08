import asyncio
import logging

from flask import Blueprint, jsonify, request, current_app
from wyoming.client import AsyncTcpClient
from wyoming.event import Event

_LOGGER = logging.getLogger(__name__)
handler = Blueprint('handler', __name__)

@handler.route("/event", methods=['POST'])
async def send_event():
    if not request.json or 'type' not in request.json:
        return jsonify({"error": "Missing event type"}), 400

    bridge_uri = current_app.config.get('BRIDGE_URI')
    if not bridge_uri:
        return jsonify({"error": "Bridge URI not configured"}), 500

    timeout = 5
    response = None

    ping_event = Event.from_dict(request.json)
    if ping_event is None:
        return jsonify({"error": "Invalid event data"}), 400
    
    for _ in range(3):
        try:
            async with AsyncTcpClient(bridge_uri['host'], bridge_uri['port']) as client, asyncio.timeout(timeout):
                await client.write_event(ping_event)
                while True:
                    pong_event = await client.read_event()
                    if pong_event is None:
                        raise Exception("Connection closed unexpectedly")

                    _LOGGER.debug("Received event: %s - %s", pong_event.type, pong_event.data)
                    response = pong_event
                    break  # while

                if response is not None:
                    break  # for
        except (TimeoutError, OSError, Exception):
            # Sleep and try again
            await asyncio.sleep(1)

    if response is None:
        return jsonify({"error": "Failed to receive event"}), 500
    
    return jsonify({"response": response}), 201


