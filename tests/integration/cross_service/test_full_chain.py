import asyncio
import json
import os
import uuid

import httpx
import pytest
import websockets


if os.getenv("RUN_CROSS_SERVICE_TESTS") != "1":
    pytest.skip(
        "cross-service tests require docker-compose; run scripts/run-integration-tests.ps1",
        allow_module_level=True,
    )


LOCATION_URL = "http://localhost:8001"
EVENT_URL = "http://localhost:8002"
NOTIFICATION_WS_URL = "ws://localhost:8003"


async def wait_for_event_message(websocket, event_id: str, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        except TimeoutError:
            return None

        payload = json.loads(message)
        if payload.get("type") == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            continue

        if payload.get("event_id") == event_id:
            return payload

    return None


async def run_demo_full_flow_nearby_users_receive_urgent_event() -> None:
    run_id = uuid.uuid4().hex[:8]
    user_near = f"cross-near-{run_id}"
    user_far = f"cross-far-{run_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        near_location = {
            "user_id": user_near,
            "latitude": 25.0173,
            "longitude": 121.5397,
        }
        far_location = {
            "user_id": user_far,
            "latitude": 25.0500,
            "longitude": 121.5600,
        }

        near_response = await client.post(f"{LOCATION_URL}/locations", json=near_location)
        far_response = await client.post(f"{LOCATION_URL}/locations", json=far_location)

        assert near_response.status_code == 200
        assert far_response.status_code == 200

        nearby_response = await client.get(
            f"{LOCATION_URL}/locations/nearby",
            params={
                "latitude": 25.0173,
                "longitude": 121.5397,
                "radius_meters": 500,
            },
        )
        assert nearby_response.status_code == 200
        assert user_near in nearby_response.json()["users"]
        assert user_far not in nearby_response.json()["users"]

        async with websockets.connect(f"{NOTIFICATION_WS_URL}/ws/{user_near}") as ws_near:
            event_response = await client.post(
                f"{EVENT_URL}/events",
                json={
                    "client_event_id": f"cross-{run_id}",
                    "title": "Cross service urgent event",
                    "message": "End-to-end notification test",
                    "latitude": 25.0173,
                    "longitude": 121.5397,
                    "severity": "urgent",
                    "radius_meters": 500,
                },
            )

            assert event_response.status_code == 200
            event_body = event_response.json()
            assert event_body["status"] == "created"
            assert event_body["delivered_count"] >= 1
            assert user_near in event_body["delivered_to"]
            assert user_far not in event_body["delivered_to"]

            notification = await wait_for_event_message(
                ws_near,
                event_body["event_id"],
                timeout=5.0,
            )

            assert notification is not None
            assert notification["title"] == "Cross service urgent event"
            assert notification["severity"] == "urgent"


def test_demo_full_flow_nearby_users_receive_urgent_event() -> None:
    asyncio.run(run_demo_full_flow_nearby_users_receive_urgent_event())


async def run_notification_websocket_has_no_cross_talk() -> None:
    run_id = uuid.uuid4().hex[:8]
    user_a = f"cross-a-{run_id}"
    user_b = f"cross-b-{run_id}"
    event_id = f"manual-{run_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        async with (
            websockets.connect(f"{NOTIFICATION_WS_URL}/ws/{user_a}") as ws_a,
            websockets.connect(f"{NOTIFICATION_WS_URL}/ws/{user_b}") as ws_b,
        ):
            notify_response = await client.post(
                f"http://localhost:8003/notify/{user_a}",
                json={
                    "event_id": event_id,
                    "title": "Only user A",
                    "message": "User B should not receive this",
                    "latitude": 25.0173,
                    "longitude": 121.5397,
                    "severity": "urgent",
                    "distance_meters": 42.0,
                },
            )

            assert notify_response.status_code == 200

            message_a = await wait_for_event_message(ws_a, event_id, timeout=5.0)
            message_b = await wait_for_event_message(ws_b, event_id, timeout=1.0)

            assert message_a is not None
            assert message_a["event_id"] == event_id
            assert message_b is None


def test_notification_websocket_has_no_cross_talk() -> None:
    asyncio.run(run_notification_websocket_has_no_cross_talk())
