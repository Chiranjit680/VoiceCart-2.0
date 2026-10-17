import { useState, useCallback, useEffect, useRef } from "react";
import { useWebSocket, type ConnectionStatus } from "@/hooks/useWebSocket";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { useHandsFree } from "@/hooks/useHandsFree";
import { useAuth } from "@/contexts/AuthContext";
import { RecordButton } from "@/components/RecordButton";
import { ConnectionIndicator } from "@/components/ConnectionIndicator";
import { ActivityLog, LogEntry } from "@/components/ActivityLog";
import { Conversation, type ConversationItem, type NewConversationItem } from "@/components/Conversation";
import { withAuthToken } from "@/lib/api";
import { parseServerMessage } from "@/lib/serverMessage";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

// Where the manager (WebSocket gateway) listens.
const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8003/ws";

// If a reply has not arrived by then, stop showing the "thinking" dots.
const REPLY_TIMEOUT_MS = 120_000;

function formatDuration(s: number) {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

let logId = 0;
let itemId = 0;
function now() {
  return new Date().toLocaleTimeString("en-US", { hour12: false });
}

export default function VoicePage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [items, setItems] = useState<ConversationItem[]>([]);
  // Requests sent and not yet answered. A count, not a flag: a second request can start before the first is answered.
  const [inFlight, setInFlight] = useState(0);
  const pending = inFlight > 0;
  const requestStarted = useCallback(() => setInFlight((n) => n + 1), []);
  const requestFinished = useCallback(() => setInFlight((n) => Math.max(0, n - 1)), []);

  const addLog = useCallback((message: string) => {
    setLogs((prev) => [...prev.slice(-200), { id: ++logId, time: now(), message }]);
  }, []);

  const addItem = useCallback((item: NewConversationItem) => {
    setItems((prev) => [...prev.slice(-100), { ...item, id: ++itemId } as ConversationItem]);
  }, []);

  const handleServerMessage = useCallback(
    (raw: string) => {
      const message = parseServerMessage(raw);
      if (message.type === "transcript") {
        addItem({ role: "user", text: message.text }); // still waiting for the reply
      } else if (message.type === "reply") {
        addItem({ role: "assistant", text: message.text, products: message.products });
        requestFinished();
      } else {
        addItem({ role: "notice", text: message.text });
        requestFinished();
      }
    },
    [addItem, requestFinished]
  );

  const { status, connect, disconnect, sendBlob, sendText } = useWebSocket(handleServerMessage);

  // Send the full Blob after recording stops
  const handleChunk = useCallback(
    async (blob: Blob) => {
      const kb = (blob.size / 1024).toFixed(1);
      const sent = await sendBlob(blob);
      addLog(sent ? `Sent audio: ${kb} KB` : `Audio ready (${kb} KB) — not connected`);
    },
    [sendBlob, addLog]
  );

  const handleRecordingStop = useCallback(() => {
    const sent = sendText("END");
    if (sent) requestStarted();
    addLog(sent ? "Sent END signal — waiting for transcription…" : "END signal not sent — not connected");
  }, [sendText, requestStarted, addLog]);

  const { isRecording, duration, start, stop } = useVoiceRecorder({
    onChunkReady: handleChunk,
    onStop: handleRecordingStop,
    // No timeslice: single Blob after stop
  });

  // Connect as soon as the user is logged in, and stay connected (the hook retries if the link drops).
  const { token } = useAuth();
  useEffect(() => {
    if (!token) return;
    connect(() => withAuthToken(WS_URL)); // a function, so every retry uses the latest token
    return () => disconnect();
  }, [token, connect, disconnect]);

  const previousStatus = useRef<ConnectionStatus>("disconnected");
  useEffect(() => {
    const was = previousStatus.current;
    previousStatus.current = status;
    if (status === "connected") addLog("Connected to the voice gateway");
    else if (was === "connected") addLog("Connection lost — reconnecting…");
    if (status !== "connected") setInFlight(0); // a reply can no longer arrive on this connection
  }, [status, addLog]);

  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => {
      setInFlight(0);
      addItem({ role: "notice", text: "That is taking too long. Please try again." });
    }, REPLY_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [inFlight, pending, addItem]);

  // Hands-free: the voice activity detector starts and stops recording by itself.
  const handleSegment = useCallback(
    async (blob: Blob) => {
      const kb = (blob.size / 1024).toFixed(1);
      const sent = await sendBlob(blob);
      if (sent) {
        sendText("END");
        requestStarted();
        addLog(`Speech detected — sent ${kb} KB, waiting for transcription…`);
      } else {
        addLog(`Speech detected (${kb} KB) — not connected`);
      }
    },
    [sendBlob, sendText, requestStarted, addLog]
  );
  const handsFree = useHandsFree({ onSegment: handleSegment });
  const { stop: stopHandsFree } = handsFree;

  // The connection can also drop on its own; don't keep the microphone open for nothing.
  useEffect(() => {
    if (status !== "connected" && handsFree.isActive) {
      stopHandsFree();
      addLog("Connection lost — hands-free turned off");
    }
  }, [status, handsFree.isActive, stopHandsFree, addLog]);

  const toggleHandsFree = useCallback(
    async (on: boolean) => {
      if (!on) {
        stopHandsFree();
        addLog("Hands-free off");
        return;
      }
      try {
        await handsFree.start();
        addLog("Hands-free on — listening for speech");
      } catch {
        addLog("Microphone access denied");
      }
    },
    [handsFree, stopHandsFree, addLog]
  );

  const toggleRecording = useCallback(async () => {
    if (isRecording) {
      stop();
      addLog("Recording stopped");
    } else {
      try { await start(); addLog("Recording started (WebM/Opus)"); }
      catch { addLog("Microphone access denied"); }
    }
  }, [isRecording, start, stop, addLog]);

  return (
    <div className="mx-auto flex h-[calc(100vh-3.5rem)] w-full max-w-3xl flex-col">
      <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
        <ConnectionIndicator status={status} />
        <div className="flex items-center gap-2">
          <Switch
            id="hands-free"
            checked={handsFree.isActive}
            disabled={status !== "connected" || isRecording}
            onCheckedChange={toggleHandsFree}
          />
          <Label htmlFor="hands-free" className="text-muted-foreground">
            Hands-free (auto-detect speech)
          </Label>
        </div>
      </div>

      <Conversation items={items} pending={pending} />

      <div className="flex flex-col items-center gap-3 border-t border-border bg-background px-4 py-4">
        <RecordButton
          isRecording={isRecording || handsFree.state === "hearing"}
          disabled={status !== "connected" || handsFree.isActive}
          onClick={toggleRecording}
        />
        {handsFree.isActive ? (
          <div className="flex w-48 flex-col items-center gap-2">
            <span className="text-sm font-medium text-foreground">
              {handsFree.state === "hearing" ? "Hearing you…" : "Listening for speech…"}
            </span>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-100"
                style={{ width: `${Math.round(handsFree.level * 100)}%` }}
              />
            </div>
          </div>
        ) : (
          <span className="tabular-nums text-sm font-medium text-muted-foreground">{formatDuration(duration)}</span>
        )}

        <details className="w-full max-w-md text-sm text-muted-foreground">
          <summary className="cursor-pointer select-none text-center">Activity</summary>
          <div className="mt-2">
            <ActivityLog entries={logs} />
          </div>
        </details>
      </div>
    </div>
  );
}
