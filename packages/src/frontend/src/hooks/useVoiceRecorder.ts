import { useState, useRef, useCallback } from "react";

interface UseVoiceRecorderOptions {
  onChunkReady?: (blob: Blob) => void;
  onStop?: () => void; // fires after the last chunk has been emitted
  timeslice?: number; // ms between chunks, undefined = single blob on stop
}

export function useVoiceRecorder({ onChunkReady, onStop, timeslice }: UseVoiceRecorderOptions = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });

    const recorder = new MediaRecorder(stream, {
      mimeType: "audio/webm;codecs=opus",
    });

    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        chunksRef.current.push(e.data);
      }
    };

    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      // Emit the single Blob after stop
      if (chunksRef.current.length > 0) {
        const fullBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        onChunkReady?.(fullBlob);
      }
      onStop?.();
      chunksRef.current = [];
    };

    recorderRef.current = recorder;
    recorder.start(); // No timeslice: single Blob on stop
    setIsRecording(true);
    setDuration(0);

    timerRef.current = setInterval(() => {
      setDuration((d) => d + 1);
    }, 1000);
  }, [onChunkReady, onStop, timeslice]);

  const stop = useCallback(() => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setIsRecording(false);
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    // chunksRef.current will be cleared in onstop
  }, []);

  return { isRecording, duration, start, stop };
}
