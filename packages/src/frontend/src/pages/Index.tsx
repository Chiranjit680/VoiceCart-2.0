import { useState, useCallback } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { RecordButton } from "@/components/RecordButton";
import { ConnectionPanel } from "@/components/ConnectionPanel";
import { ActivityLog, LogEntry } from "@/components/ActivityLog";
import { MessageBox, Message } from "@/components/MessageBox";
import { AudioLines } from "lucide-react";

function formatDuration(s: number) {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

let logId = 0;
let msgId = 0;
function now() {
  return new Date().toLocaleTimeString("en-US", { hour12: false });
}

const Index = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);

  const addLog = useCallback((message: string) => {
    setLogs((prev) => [...prev.slice(-200), { id: ++logId, time: now(), message }]);
  }, []);

  const handleServerMessage = useCallback((text: string) => {
    setMessages((prev) => [...prev.slice(-200), { id: ++msgId, time: now(), text }]);
  }, []);

  const { status, connect, disconnect, sendBlob } = useWebSocket(handleServerMessage);

  const handleChunk = useCallback(
    async (blob: Blob) => {
      const kb = (blob.size / 1024).toFixed(1);
      const sent = await sendBlob(blob);
      addLog(sent ? `Sent chunk: ${kb} KB` : `Chunk ready (${kb} KB) — not connected`);
    },
    [sendBlob, addLog]
  );

  const { isRecording, duration, start, stop } = useVoiceRecorder({
    onChunkReady: handleChunk,
    timeslice: 1000,
  });

  const handleConnect = useCallback(
    (url: string) => {
      addLog(`Connecting to ${url}…`);
      connect(url);
    },
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
      try {
        await start();
        addLog("Recording started (WebM/Opus, 1s chunks)");
      } catch {
        addLog("Microphone access denied");
      }
    }
  }, [isRecording, start, stop, addLog]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-10 bg-background px-4 py-12">
      <div className="flex flex-col items-center gap-2">
        <AudioLines className="h-8 w-8 text-primary" />
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Voice Stream</h1>
        <p className="text-sm text-muted-foreground">Capture &amp; stream audio over WebSocket</p>
      </div>

      <ConnectionPanel status={status} onConnect={handleConnect} onDisconnect={handleDisconnect} />

      <div className="flex flex-col items-center gap-4">
        <RecordButton isRecording={isRecording} disabled={status !== "connected"} onClick={toggleRecording} />
        <span className="tabular-nums text-lg font-medium text-foreground">
          {formatDuration(duration)}
        </span>
      </div>

      <MessageBox messages={messages} />
      <ActivityLog entries={logs} />
    </div>
  );
};

export default Index;
