import { useState, useRef, useCallback, useEffect } from "react";

const STORAGE_KEY = "voicecart_speak_replies";

function readPreference(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "off"; // on unless the shopper turned it off
  } catch {
    return true;
  }
}

/**
 * Plays the spoken version of the assistant's replies. `enabled` is the shopper's switch (remembered on this device);
 * `speaking` is true while audio is playing, so the microphone can be held back and not hear the speaker.
 */
export function useSpeech() {
  const [enabled, setEnabledState] = useState(readPreference);
  const [speaking, setSpeaking] = useState(false);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stop = useCallback(() => {
    const audio = audioRef.current;
    audioRef.current = null;
    if (audio) {
      audio.onended = audio.onerror = null;
      audio.pause();
    }
    setSpeaking(false);
  }, []);

  const play = useCallback(
    (mime: string, base64: string) => {
      if (!enabledRef.current) return;
      stop(); // a newer reply replaces one still being read
      const audio = new Audio(`data:${mime};base64,${base64}`);
      audioRef.current = audio;
      const done = () => {
        if (audioRef.current === audio) {
          audioRef.current = null;
          setSpeaking(false);
        }
      };
      audio.onended = done;
      audio.onerror = done;
      setSpeaking(true);
      // Browsers refuse autoplay before the page has had a click; the text is on screen anyway.
      audio.play().catch(done);
    },
    [stop]
  );

  const setEnabled = useCallback(
    (value: boolean) => {
      setEnabledState(value);
      try {
        localStorage.setItem(STORAGE_KEY, value ? "on" : "off");
      } catch {
        // not remembered; still applies for this visit
      }
      if (!value) stop();
    },
    [stop]
  );

  useEffect(() => stop, [stop]);

  return { enabled, setEnabled, speaking, play, stop };
}
