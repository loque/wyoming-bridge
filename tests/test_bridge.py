import pytest
import asyncio

from wyoming.info import Attribution, Info, WakeProgram, WakeModel
from wyoming.wake import Detect
from wyoming.event import Event
from wyoming.client import AsyncClient
from wyoming.server import AsyncServer, AsyncEventHandler

from wake_bridge.handler import WakeBridgeEventHandler
from wake_bridge import __version__

# Dummy info for handler
wyoming_info = Info(
    wake=[
        WakeProgram(
            name="wyoming-wake-bridge",
            description="Wyoming Wake Bridge",
            attribution=Attribution(
                name="loque", url="https://github.com/loque/wyoming-bridge"
            ),
            installed=True,
            version=__version__,
            models=[
                WakeModel(
                    name="hey jarvis",
                    description="A wake word model for Hey Jarvis",
                    phrase="hey jarvis",
                    attribution=Attribution(
                        name="dscripka",
                        url="https://github.com/dscripka/openWakeWord",
                    ),
                    installed=True,
                    languages=[],
                    version="0.1.0",
                )
            ],
        )
    ],
)


@pytest.mark.asyncio
async def test_server_bridge_client_communication():
    """
    Test server -> bridge -> client communication.
    """
    server_uri = "tcp://127.0.0.1:6000"
    bridge_uri = "tcp://127.0.0.1:6001"

    # Start a dummy wake server
    wake_server = AsyncServer.from_uri(server_uri)
    wake_server_received = {}

    class DummyWakeHandler(AsyncEventHandler):
        async def handle_event(self, event: Event) -> bool:
            wake_server_received['event'] = event
            # Echo back for reverse test
            await self.write_event(event)
            return True

    wake_server_task = asyncio.create_task(
        wake_server.run(lambda *a, **kw: DummyWakeHandler(*a, **kw)))
    await asyncio.sleep(0.1)  # Ensure server is listening

    # Start the bridge (as a handler)
    wake_client = AsyncClient.from_uri(server_uri)
    await wake_client.connect()
    bridge_server = AsyncServer.from_uri(bridge_uri)

    def bridge_handler_factory(*a, **kw):
        return WakeBridgeEventHandler(wyoming_info, wake_client, *a, **kw)
    bridge_task = asyncio.create_task(
        bridge_server.run(bridge_handler_factory))
    await asyncio.sleep(0.1)  # Ensure bridge is listening

    # Start a client to connect to the bridge
    client = AsyncClient.from_uri(bridge_uri)
    await client.connect()

    # Send a Detect event from client -> bridge -> server
    detect = Detect(names=["test"])
    await client.write_event(detect.event())
    await asyncio.sleep(0.1)
    assert wake_server_received['event'] is not None
    assert Detect.is_type(wake_server_received['event'].type)
    received_detect = Detect.from_event(wake_server_received['event'])
    assert received_detect.names == ["test"]

    # Clean up
    await client.disconnect()
    await bridge_server.stop()
    await wake_client.disconnect()
    await wake_server.stop()
    wake_server_task.cancel()
    bridge_task.cancel()


@pytest.mark.asyncio
async def test_server_bridge_client_reverse_communication():
    """
    Test server <- bridge <- client communication.
    """
    server_uri = "tcp://127.0.0.1:6010"
    bridge_uri = "tcp://127.0.0.1:6011"

    # Start a dummy wake server
    wake_server = AsyncServer.from_uri(server_uri)

    class DummyWakeHandler(AsyncEventHandler):
        async def handle_event(self, event: Event) -> bool:
            # Echo back
            await self.write_event(event)
            return True

    wake_server_task = asyncio.create_task(
        wake_server.run(lambda *a, **kw: DummyWakeHandler(*a, **kw)))
    await asyncio.sleep(0.1)  # Ensure server is listening

    # Start the bridge (as a handler)
    wake_client = AsyncClient.from_uri(server_uri)
    await wake_client.connect()
    bridge_server = AsyncServer.from_uri(bridge_uri)

    def bridge_handler_factory(*a, **kw):
        return WakeBridgeEventHandler(wyoming_info, wake_client, *a, **kw)
    bridge_task = asyncio.create_task(
        bridge_server.run(bridge_handler_factory))
    await asyncio.sleep(0.1)  # Ensure bridge is listening

    # Start a client to connect to the bridge
    client = AsyncClient.from_uri(bridge_uri)
    await client.connect()

    # Send a Detect event from client -> bridge -> server, expect echo back
    detect = Detect(names=["test-reverse"])
    await client.write_event(detect.event())
    response = await client.read_event()
    assert response is not None
    assert Detect.is_type(response.type)
    received_detect = Detect.from_event(response)
    assert received_detect.names == ["test-reverse"]

    # Clean up
    await client.disconnect()
    await bridge_server.stop()
    await wake_client.disconnect()
    await wake_server.stop()
    wake_server_task.cancel()
    bridge_task.cancel()
