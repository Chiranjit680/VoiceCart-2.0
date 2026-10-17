import { useState, useRef, useCallback, useEffect } from "react";

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

/** Close code the manager uses for "log in again". Retrying would only fail the same way. */
export const CLOSE_AUTH_FAILED = 4401;

const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 15000];

type UrlSource = string | (() => string);

/**
 * WebSocket that stays connected: after `connect()`, an unexpected close is retried with a growing
 * delay until `disconnect()` is called. Pass a function as the URL to rebuild it on every attempt,
 * e.g. so a retry picks up a token the user has refreshed in the meantime.
 */
export function useWebSocket(onMessage?: (data: string) => void) {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const urlRef = useRef<UrlSource | null>(null); // null = nobody wants a connection
  const retryRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const open = useCallback(() => {
    const source = urlRef.current;
    if (!source) return;
    setStatus("connecting");

    const ws = new WebSocket(typeof source === "function" ? source() : source);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    // Every handler ignores sockets that have been replaced or closed on purpose.
    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      retryRef.current = 0;
      setStatus("connected");
    };
    ws.onerror = () => {
      if (wsRef.current === ws) setStatus("error");
    };
    ws.onmessage = (event) => {
      if (wsRef.current !== ws) return;
      const text = typeof event.data === "string" ? event.data : new TextDecoder().decode(event.data);
      onMessageRef.current?.(text);
    };
    ws.onclose = (event) => {
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      if (!urlRef.current) {
        setStatus("disconnected");
        return;
      }
      if (event.code === CLOSE_AUTH_FAILED) {
        urlRef.current = null; // the user has to log in again; do not hammer the server
        setStatus("error");
        return;
      }
      const delay = RETRY_DELAYS_MS[Math.min(retryRef.current++, RETRY_DELAYS_MS.length - 1)];
      setStatus("connecting");
      timerRef.current = setTimeout(open, delay);
    };
  }, []);

  const connect = useCallback(
    (url: UrlSource) => {
      urlRef.current = url;
      retryRef.current = 0;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      const state = wsRef.current?.readyState;
      if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) return;
      open();
    },
    [open]
  );

  const disconnect = useCallback(() => {
    urlRef.current = null;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    const ws = wsRef.current;
    wsRef.current = null; // before close(), so onclose knows this was on purpose
    ws?.close();
    setStatus("disconnected");
  }, []);

  useEffect(() => disconnect, [disconnect]);

  const sendBlob = useCallback(async (blob: Blob) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not connected");
      return false;
    }
    const buffer = await blob.arrayBuffer();
    ws.send(buffer);
    console.log(`Sent ${buffer.byteLength} bytes`);
    return true;
  }, []);

  const sendText = useCallback((text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not connected");
      return false;
    }
    ws.send(text);
    console.log(`Sent text: ${text}`);
    return true;
  }, []);

  return { status, connect, disconnect, sendBlob, sendText };
}
