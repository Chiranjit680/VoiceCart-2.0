from fastapi import FastAPI, UploadFile, File
from faster_whisper import WhisperModel
import os

app = FastAPI()

# CONFIGURATION
# "tiny" or "base" are best for real-time CPU. "small" might be too slow (~1-2s latency).
# compute_type="int8" is the magic key for CPU speed.
model_size = "base.en" 
model = WhisperModel(model_size, device="cpu", compute_type="int8")

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    # faster-whisper accepts a binary file-like object directly!
    # No need to save to disk.
    
    segments, info = model.transcribe(file.file, beam_size=5)
    
    # "segments" is a generator. We must iterate to run the inference.
    text = " ".join([segment.text for segment in segments])
    
    return {
        "text": text.strip(),
        "language": info.language,
        "probability": info.language_probability
    }

if __name__ == "__main__":
    import uvicorn
    # Run on port 8001 to separate it from the Manager
    uvicorn.run(app, host="0.0.0.0", port=8001)


    """
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

# URL of your STT Microservice
STT_SERVICE_URL = "http://localhost:8001/transcribe"

@app.websocket("/ws/audio")
async def audio_websocket(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")
    
    try:
        while True:
            # 1. Receive Audio Blob from Client (Browser/App)
            # Expecting raw bytes (blob) from the frontend
            audio_data = await websocket.receive_bytes()
            
            # 2. Call STT Microservice
            # We use httpx to post the bytes as a "file" to the STT service
            async with httpx.AsyncClient() as client:
                files = {'file': ('audio.wav', audio_data, 'audio/wav')}
                response = await client.post(STT_SERVICE_URL, files=files)
            
            if response.status_code == 200:
                transcription = response.json().get("text")
                print(f"User said: {transcription}")
                
                # 3. (Optional) Send text back to client for confirmation
                await websocket.send_text(f"You said: {transcription}")
                
                # ... Next: Send 'transcription' to your Agent/LLM ...
            else:
                print("STT Error:", response.text)

    except WebSocketDisconnect:
        print("Client disconnected")
    """


# Test code for direct WebSocket STT (no HTTP intermediary)

# from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
# from faster_whisper import WhisperModel
# import io
# import uvicorn

# app = FastAPI()

# # CONFIGURATION
# # Using "base.en" and "int8" for CPU optimization as requested
# model_size = "base.en"
# print(f"Loading Whisper Model: {model_size} on CPU...")
# model = WhisperModel(model_size, device="cpu", compute_type="int8")
# print("Model Loaded!")

# @app.websocket("/ws/audio")
# async def websocket_endpoint(websocket: WebSocket):
#     """
#     WebSocket Endpoint for direct testing.
#     Accepts raw audio bytes, transcribes, and returns text.
#     """
#     await websocket.accept()
#     print("Client connected via WebSocket")

#     try:
#         while True:
#             # 1. Receive raw audio bytes from the test script
#             data = await websocket.receive_bytes()
            
#             print(f"Received audio data: {len(data)} bytes")

#             # 2. Wrap bytes in a file-like object for Faster-Whisper
#             # (No disk I/O involved here, purely RAM)
#             audio_stream = io.BytesIO(data)

#             # 3. Transcribe
#             # beam_size=5 provides better accuracy; lower it (e.g., 1) for speed if needed
#             segments, info = model.transcribe(audio_stream, beam_size=5)

#             # 4. Collect result
#             text = " ".join([segment.text for segment in segments]).strip()
            
#             # 5. Send back to client
#             if text:
#                 print(f"Transcribed: {text}")
#                 await websocket.send_text(text)
#             else:
#                 await websocket.send_text("[Silence or Unclear]")

#     except WebSocketDisconnect:
#         print("Client disconnected")
#     except Exception as e:
#         print(f"Error: {e}")
#         await websocket.close()

# # Keep the HTTP endpoint if you still need it for the future architecture
# @app.post("/transcribe")
# async def transcribe_audio(file: UploadFile = File(...)):
#     segments, info = model.transcribe(file.file, beam_size=5)
#     text = " ".join([segment.text for segment in segments])
#     return {"text": text.strip()}

# if __name__ == "__main__":
#     # CHANGED PORT: 8000 (Matches your URI="ws://localhost:8000/ws/audio")
#     uvicorn.run(app, host="0.0.0.0", port=8000)