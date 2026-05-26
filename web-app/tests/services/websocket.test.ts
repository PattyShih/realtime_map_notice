import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createNotificationSocket } from "../../src/services/websocket";
import type { EventNotification } from "../../src/types/api";

class MockWebSocket {
  static readonly OPEN = 1;
  static instances: MockWebSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = MockWebSocket.OPEN;
  sentMessages: string[] = [];

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this);
  }

  send(message: string) {
    this.sentMessages.push(message);
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  open() {
    this.onopen?.();
  }

  receive(data: string) {
    this.onmessage?.({ data } as MessageEvent<string>);
  }

  closeFromServer() {
    this.close();
  }
}

const notification: EventNotification = {
  event_id: "evt-1",
  title: "Road blocked",
  message: "Road blocked near library",
  latitude: 25.0173,
  longitude: 121.5397,
  severity: "urgent",
  distance_meters: 42.5,
};

describe("createNotificationSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("connects to the user notification route", () => {
    const socket = createNotificationSocket("u-1", vi.fn());

    expect(MockWebSocket.instances[0].url).toBe("ws://localhost:8003/ws/u-1");

    socket.destroy();
  });

  it("responds to server ping with pong", () => {
    const socket = createNotificationSocket("u-1", vi.fn());
    const ws = MockWebSocket.instances[0];

    ws.receive(JSON.stringify({ type: "ping" }));

    expect(ws.sentMessages).toEqual([JSON.stringify({ type: "pong" })]);

    socket.destroy();
  });

  it("passes valid event notifications to the callback", () => {
    const onNotification = vi.fn();
    const socket = createNotificationSocket("u-1", onNotification);
    const ws = MockWebSocket.instances[0];

    ws.receive(JSON.stringify(notification));
    ws.receive("not json");

    expect(onNotification).toHaveBeenCalledTimes(1);
    expect(onNotification).toHaveBeenCalledWith(notification);

    socket.destroy();
  });

  it("updates connection status and reconnects after close", () => {
    const onStatusChange = vi.fn();
    const socket = createNotificationSocket("u-1", vi.fn(), onStatusChange);
    const firstConnection = MockWebSocket.instances[0];

    firstConnection.open();
    firstConnection.closeFromServer();

    expect(onStatusChange).toHaveBeenNthCalledWith(1, true);
    expect(onStatusChange).toHaveBeenNthCalledWith(2, false);

    vi.advanceTimersByTime(1000);

    expect(MockWebSocket.instances).toHaveLength(2);

    socket.destroy();
  });
});
