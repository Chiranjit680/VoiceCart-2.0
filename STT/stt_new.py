from fastapi import FastAPI, UploadFile, File, Form
from gnani.stt import GnaniSTTClient
import tempfile
import subprocess
import os
from pathlib import Path
from dotenv import load_dotenv

# Load STT/.env regardless of the directory the script is launched from
load_dotenv(Path(__file__).resolve().parent / ".env")

app = FastAPI()

GNANI_API_KEY = os.environ.get("GNANI_API_KEY")
DEFAULT_LANGUAGE = os.environ.get("GNANI_LANGUAGE_CODE", "en-IN")

if not GNANI_API_KEY:
    raise RuntimeError("GNANI_API_KEY environment variable is not set")

client = GnaniSTTClient(api_key=GNANI_API_KEY)

@app.post("/transcribe")
def transcribe_audio(
    file: UploadFile = File(...),
    language_code: str = Form(DEFAULT_LANGUAGE),
):
    tmp_webm_path = None
    tmp_wav_path = None
    try:
        # Save uploaded file
        suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
        tmp_webm = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_webm.write(file.file.read())
        tmp_webm.close()
        tmp_webm_path = tmp_webm.name

        # Convert to 16kHz mono WAV using ffmpeg
        tmp_wav_path = tmp_webm_path + ".wav"
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", tmp_webm_path,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                tmp_wav_path
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            print("ffmpeg error:", result.stderr)
            return {"text": "", "error": "Audio conversion failed"}

        # Transcribe the clean WAV via Gnani API
        response = client.transcribe(tmp_wav_path, language_code=language_code)
        text = (response.get("transcript") or "").strip()
        return {"text": text, "language": language_code}

    except Exception as e:
        print("STT error:", e)
        return {"text": "", "error": str(e)}
    finally:
        for path in (tmp_webm_path, tmp_wav_path):
            try:
                if path and os.path.exists(path):
                    os.unlink(path)
            except Exception:
                pass

if __name__ == "__main__":
    import uvicorn
    # Run on port 8001 to separate it from the Manager
    uvicorn.run(app, host="0.0.0.0", port=8001)
