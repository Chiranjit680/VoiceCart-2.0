import { useState, useRef, useCallback } from "react";

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export function useWebSocket(onMessage?: (data: string) => void) {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback((url: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setStatus("connecting");

    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => setStatus("connected");
    ws.onclose = () => {
      setStatus("disconnected");
      wsRef.current = null;
    };
    ws.onerror = () => setStatus("error");
    ws.onmessage = (event) => {
      const text = typeof event.data === "string" ? event.data : new TextDecoder().decode(event.data);
      onMessageRef.current?.(text);
    };

    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("disconnected");
  }, []);

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
