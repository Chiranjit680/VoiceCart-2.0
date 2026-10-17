import sys
import time
import httpx

# 1. Configuration
URL = "http://localhost:8001/transcribe"
AUDIO_FILE = sys.argv[1] if len(sys.argv) > 1 else "test_audio.wav"  # Make sure this file exists!
LANGUAGE_CODE = sys.argv[2] if len(sys.argv) > 2 else None  # None -> server default

def test_transcription():
    print(f"Posting {AUDIO_FILE} to {URL} (language={LANGUAGE_CODE or 'server default'})...")

    # 2. Read audio file into memory
    with open(AUDIO_FILE, "rb") as f:
        audio_data = f.read()

    # 3. Start timer for latency check
    start_time = time.time()

    # 4. Send the audio as multipart form data
    response = httpx.post(
        URL,
        files={"file": (AUDIO_FILE, audio_data, "audio/wav")},
        data={"language_code": LANGUAGE_CODE} if LANGUAGE_CODE else None,
        timeout=60,
    )
    end_time = time.time()

    print("\n--- Result ---")
    print(f"Status: {response.status_code}")
    print(f"Server Response: {response.json()}")
    print(f"Total Latency: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    test_transcription()
