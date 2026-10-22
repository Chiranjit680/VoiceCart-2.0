import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSpeech } from "./useSpeech";

class FakeAudio {
  static last: FakeAudio | null = null;
  static all: FakeAudio[] = [];
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  paused = false;
  constructor(public src: string) {
    FakeAudio.last = this;
    FakeAudio.all.push(this);
  }
  play = vi.fn(async () => {});
  pause() {
    this.paused = true;
  }
}

describe("useSpeech", () => {
  beforeEach(() => {
    FakeAudio.last = null;
    FakeAudio.all = [];
    localStorage.clear();
    vi.stubGlobal("Audio", FakeAudio);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("plays a reply and reports speaking until it ends", () => {
    const { result } = renderHook(() => useSpeech());
    act(() => result.current.play("audio/wav", "AAAA"));
    expect(FakeAudio.last?.src).toBe("data:audio/wav;base64,AAAA");
    expect(result.current.speaking).toBe(true);
    act(() => FakeAudio.last!.onended!());
    expect(result.current.speaking).toBe(false);
  });

  it("replaces a reply that is still playing with a newer one", () => {
    const { result } = renderHook(() => useSpeech());
    act(() => result.current.play("audio/wav", "AAAA"));
    const first = FakeAudio.last!;
    act(() => result.current.play("audio/wav", "BBBB"));
    expect(first.paused).toBe(true);
    act(() => first.onended?.()); // the old one finishing late changes nothing
    expect(result.current.speaking).toBe(true);
  });

  it("plays nothing when the shopper turned speech off, and remembers the choice", () => {
    const { result, unmount } = renderHook(() => useSpeech());
    act(() => result.current.setEnabled(false));
    act(() => result.current.play("audio/wav", "AAAA"));
    expect(FakeAudio.all).toHaveLength(0);
    unmount();
    expect(renderHook(() => useSpeech()).result.current.enabled).toBe(false);
  });

  it("stops what is playing when switched off", () => {
    const { result } = renderHook(() => useSpeech());
    act(() => result.current.play("audio/wav", "AAAA"));
    act(() => result.current.setEnabled(false));
    expect(FakeAudio.last!.paused).toBe(true);
    expect(result.current.speaking).toBe(false);
  });

  it("is not stuck 'speaking' when the browser refuses to play", async () => {
    const { result } = renderHook(() => useSpeech());
    vi.stubGlobal("Audio", class extends FakeAudio {
      play = vi.fn(async () => { throw new Error("NotAllowedError"); });
    });
    await act(async () => result.current.play("audio/wav", "AAAA"));
    expect(result.current.speaking).toBe(false);
  });
});
