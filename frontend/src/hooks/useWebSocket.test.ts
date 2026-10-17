import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket, CLOSE_AUTH_FAILED } from "./useWebSocket";

/** Minimal stand-in for the browser WebSocket that lets a test open, drop and inspect connections. */
class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  binaryType = "";
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: unknown) {
    this.sent.push(data);
  }
  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code: 1000 });
  }
  // --- test controls ---
  serverOpens() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  serverDrops(code = 1006) {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code });
  }
}

const last = () => FakeWebSocket.instances[FakeWebSocket.instances.length - 1];

describe("useWebSocket auto-reconnect", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("connects and reports the status", () => {
    const { result } = renderHook(() => useWebSocket());
    expect(result.current.status).toBe("disconnected");
    act(() => result.current.connect("ws://x/ws"));
    expect(result.current.status).toBe("connecting");
    act(() => last().serverOpens());
    expect(result.current.status).toBe("connected");
  });

  it("reconnects after an unexpected drop, waiting longer each time", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => result.current.connect("ws://x/ws"));
    act(() => last().serverOpens());

    act(() => last().serverDrops());
    expect(result.current.status).toBe("connecting");
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => vi.advanceTimersByTime(999));
    expect(FakeWebSocket.instances).toHaveLength(1); // first retry waits 1s
    act(() => vi.advanceTimersByTime(1));
    expect(FakeWebSocket.instances).toHaveLength(2);

    act(() => last().serverDrops()); // never opened: the next wait is longer (2s)
    act(() => vi.advanceTimersByTime(1999));
    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1));
    expect(FakeWebSocket.instances).toHaveLength(3);

    act(() => last().serverOpens());
    expect(result.current.status).toBe("connected");
  });

  it("starts the backoff over once a connection succeeds", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => result.current.connect("ws://x/ws"));
    act(() => last().serverDrops());
    act(() => vi.advanceTimersByTime(1000));
    act(() => last().serverOpens()); // success resets the counter
    act(() => last().serverDrops());
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it("does not reconnect after disconnect()", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => result.current.connect("ws://x/ws"));
    act(() => last().serverOpens());
    act(() => result.current.disconnect());
    expect(result.current.status).toBe("disconnected");
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("cancels a pending retry when disconnect() is called", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => result.current.connect("ws://x/ws"));
    act(() => last().serverDrops());
    act(() => result.current.disconnect());
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("gives up when the server says the login is no longer valid", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => result.current.connect("ws://x/ws"));
    act(() => last().serverDrops(CLOSE_AUTH_FAILED));
    expect(result.current.status).toBe("error");
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("rebuilds the URL on every attempt, so a retry can use a fresh token", () => {
    let token = "old";
    const { result } = renderHook(() => useWebSocket());
    act(() => result.current.connect(() => `ws://x/ws?token=${token}`));
    expect(last().url).toBe("ws://x/ws?token=old");
    token = "new";
    act(() => last().serverDrops());
    act(() => vi.advanceTimersByTime(1000));
    expect(last().url).toBe("ws://x/ws?token=new");
  });

  it("ignores late events from a socket that was replaced", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() => useWebSocket(onMessage));
    act(() => result.current.connect("ws://x/ws"));
    const first = last();
    act(() => first.serverOpens());
    act(() => result.current.disconnect());
    act(() => result.current.connect("ws://x/ws"));
    act(() => first.onmessage?.({ data: "stale" }));
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("sends text only while open", () => {
    const { result } = renderHook(() => useWebSocket());
    act(() => result.current.connect("ws://x/ws"));
    expect(result.current.sendText("END")).toBe(false);
    act(() => last().serverOpens());
    expect(result.current.sendText("END")).toBe(true);
    expect(last().sent).toEqual(["END"]);
  });
});
