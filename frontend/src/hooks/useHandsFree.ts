import { useState, useRef, useCallback, useEffect } from "react";
import { SpeechDetector, type SpeechDetectorConfig } from "@/lib/speechDetector";

export type HandsFreeState = "off" | "listening" | "hearing";

interface UseHandsFreeOptions {
  /** Called with the recorded audio (WebM/Opus) once an utterance has ended. */
  onSegment: (blob: Blob) => void;
  vad?: Partial<SpeechDetectorConfig>;
  /** While true the microphone stays open but nothing is detected or recorded (e.g. while a reply is being spoken). */
  paused?: boolean;
}

const FRAME_MS = 30;

/**
 * Hands-free recording: keeps the microphone open and records an utterance automatically,
 * starting when the voice activity detector hears speech and stopping after it falls silent.
 */
export function useHandsFree({ onSegment, vad, paused = false }: UseHandsFreeOptions) {
  const [state, setState] = useState<HandsFreeState>("off");
  const [level, setLevel] = useState(0); // 0..1, for a level meter
  const onSegmentRef = useRef(onSegment);
  onSegmentRef.current = onSegment;
  const vadRef = useRef(vad);
  vadRef.current = vad;
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const teardownRef = useRef<(() => void) | null>(null);

  const stop = useCallback(() => {
    teardownRef.current?.();
    teardownRef.current = null;
    setState("off");
    setLevel(0);
  }, []);

  const start = useCallback(async () => {
    if (teardownRef.current) return;

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    const audioContext = new AudioContext();
    await audioContext.resume(); // needs the user gesture that called start()
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);

    const detector = new SpeechDetector(vadRef.current);
    let current: { recorder: MediaRecorder; chunks: Blob[]; send: boolean } | null = null;

    const beginRecording = () => {
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      const segment = { recorder, chunks: [] as Blob[], send: false };
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) segment.chunks.push(e.data);
      };
      recorder.onstop = () => {
        if (segment.send && segment.chunks.length > 0) {
          onSegmentRef.current(new Blob(segment.chunks, { type: "audio/webm" }));
        }
      };
      recorder.start();
      current = segment;
    };

    const endRecording = (send: boolean) => {
      if (!current) return;
      current.send = send;
      if (current.recorder.state !== "inactive") current.recorder.stop();
      current = null;
    };

    let frame = 0;
    const timer = setInterval(() => {
      if (pausedRef.current) {
        // Our own speaker would otherwise be heard as the shopper talking.
        endRecording(false);
        detector.reset();
        setState("listening");
        setLevel(0);
        return;
      }
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
      const rms = Math.sqrt(sum / samples.length);

      if (++frame % 3 === 0) setLevel(Math.min(1, rms * 6)); // ~11 updates/s is plenty for a meter

      const action = detector.process(rms, performance.now());
      if (!action) return;
      switch (action.type) {
        case "start":
          beginRecording();
          break;
        case "speech":
          setState("hearing");
          break;
        case "discard":
          endRecording(false);
          break;
        case "end":
          endRecording(action.send);
          setState("listening");
          break;
      }
    }, FRAME_MS);

    teardownRef.current = () => {
      clearInterval(timer);
      endRecording(false); // an unfinished utterance is dropped when listening is switched off
      stream.getTracks().forEach((t) => t.stop());
      void audioContext.close();
    };
    setState("listening");
  }, []);

  // Release the microphone if the page goes away while listening.
  useEffect(() => () => stop(), [stop]);

  return { state, level, isActive: state !== "off", start, stop };
}
