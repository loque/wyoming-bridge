from flask import Blueprint, jsonify, request, current_app
from wyoming.client import AsyncClient
from wyoming.event import Event

handler = Blueprint('handler', __name__)

@handler.route("/event", methods=['POST'])
async def send_event():
    if not request.json or 'type' not in request.json:
        return jsonify({"error": "Missing event type"}), 400

    bridge = current_app.config.get('BRIDGE_CLIENT')
    if not isinstance(bridge, AsyncClient):
        return jsonify({"error": "Bridge client not configured"}), 500

    event = Event.from_dict(request.json)
    if not event:
        return jsonify({"error": "Invalid event data"}), 400
    
    await bridge.write_event(event)
    
    return jsonify({"message": "Event sent"}), 201


