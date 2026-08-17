import asyncio
import time

import pytest
from fastapi import WebSocketDisconnect

from tests.unit.service_loader import load_service_module


class FakeHeartbeatWebSocket:
    def __init__(self) -> None:
        self.close_args: tuple[int, str] | None = None

    async def close(self, code: int, reason: str) -> None:
        self.close_args = (code, reason)


class FakeReceiveWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages

    async def receive_text(self) -> str:
        if not self.messages:
            raise WebSocketDisconnect()
        return self.messages.pop(0)


def test_user_channel_uses_user_specific_notification_channel() -> None:
    module = load_service_module("notification-service")

    assert (
        module.user_channel("u-1")
        == "realtime_map_notice:user:u-1:notifications"
    )


def test_receive_client_messages_updates_last_pong_time() -> None:
    module = load_service_module("notification-service")
    state = module.ConnectionState(last_pong_at=0)

    with pytest.raises(WebSocketDisconnect):
        asyncio.run(
            module.receive_client_messages(
                FakeReceiveWebSocket(['{"type":"pong"}']),
                state,
            ),
        )

    assert state.last_pong_at > 0


def test_send_heartbeat_closes_stale_connection() -> None:
    module = load_service_module("notification-service")
    module.HEARTBEAT_INTERVAL_SECONDS = 0
    websocket = FakeHeartbeatWebSocket()
    state = module.ConnectionState(
        last_pong_at=time.monotonic() - module.HEARTBEAT_TIMEOUT_SECONDS - 1,
    )

    asyncio.run(module.send_heartbeat(websocket, asyncio.Lock(), state))

    assert websocket.close_args == (1001, "heartbeat timeout")
