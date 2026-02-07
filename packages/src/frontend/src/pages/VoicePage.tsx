import { useState, useCallback } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { RecordButton } from "@/components/RecordButton";
import { ConnectionPanel } from "@/components/ConnectionPanel";
import { ActivityLog, LogEntry } from "@/components/ActivityLog";
import { MessageBox, Message } from "@/components/MessageBox";

function formatDuration(s: number) {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

let logId = 0;
let msgId = 0;
function now() {
  return new Date().toLocaleTimeString("en-US", { hour12: false });
}

export default function VoicePage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);

  const addLog = useCallback((message: string) => {
    setLogs((prev) => [...prev.slice(-200), { id: ++logId, time: now(), message }]);
  }, []);

  const handleServerMessage = useCallback((text: string) => {
    setMessages((prev) => [...prev.slice(-200), { id: ++msgId, time: now(), text }]);
  }, []);

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
    addLog(sent ? "Sent END signal — waiting for transcription…" : "END signal not sent — not connected");
  }, [sendText, addLog]);

  const { isRecording, duration, start, stop } = useVoiceRecorder({
    onChunkReady: handleChunk,
    onStop: handleRecordingStop,
    // No timeslice: single Blob after stop
  });

  const handleConnect = useCallback(
    (url: string) => { addLog(`Connecting to ${url}…`); connect(url); },
    [connect, addLog]
  );

  const handleDisconnect = useCallback(() => {
    if (isRecording) stop();
    disconnect();
    addLog("Disconnected");
  }, [disconnect, isRecording, stop, addLog]);

  const toggleRecording = useCallback(async () => {
    if (isRecording) {
      stop();
      addLog("Recording stopped");
    } else {
      try { await start(); addLog("Recording started (WebM/Opus, 1s chunks)"); }
      catch { addLog("Microphone access denied"); }
    }
  }, [isRecording, start, stop, addLog]);

  return (
    <div className="flex flex-col items-center gap-10 p-6 lg:p-8 py-12">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-foreground">Voice Assistant</h1>
        <p className="mt-1 text-muted-foreground">Capture & stream audio over WebSocket</p>
      </div>

      <ConnectionPanel status={status} onConnect={handleConnect} onDisconnect={handleDisconnect} />

      <div className="flex flex-col items-center gap-4">
        <RecordButton isRecording={isRecording} disabled={status !== "connected"} onClick={toggleRecording} />
        <span className="tabular-nums text-lg font-medium text-foreground">{formatDuration(duration)}</span>
      </div>

      <MessageBox messages={messages} />
      <ActivityLog entries={logs} />
    </div>
  );
}
