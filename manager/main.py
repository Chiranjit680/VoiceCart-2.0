import os
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

load_dotenv()

STT_URL = os.getenv("STT_SERVICE_URL")
AGENT_URL = os.getenv("AGENT_SERVICE_URL")

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # We use a single async client for efficiency
    async with httpx.AsyncClient() as client:
        try:
            while True:
                # 1. Receive Audio from Client (as bytes)
                # The client should send the raw file bytes or a binary blob
                audio_data = await websocket.receive_bytes()
                print(f"Received audio data: {len(audio_data)} bytes")

                # 2. Send Audio to STT Service
                # We assume the STT service expects a file upload named 'file'
                try:
                    stt_response = await client.post(
                        STT_URL,
                        files={'file': ('audio.wav', audio_data, 'audio/wav')}
                    )
                    stt_response.raise_for_status()

                    transcribed_text = stt_response.json().get("text", "")
                    print(f"STT Transcript: {transcribed_text}")
                    
                except Exception as e:
                    print(f"STT Error: {e}")
                    await websocket.send_text("Error processing speech.")
                    continue

                # 3. Send Transcribed Text to Agent Service
                # We assume Agent expects JSON: {"input_text": "..."}
                try:
                    agent_response = await client.post(
                        AGENT_URL,
                        json={"msg": transcribed_text}
                    )
                    agent_response.raise_for_status()

                    agent_reply = agent_response.json().get("response", "")
                    print(f"Agent Reply: {agent_reply}")

                except Exception as e:
                    print(f"Agent Error: {e}")
                    await websocket.send_text("Error connecting to agent.")
                    continue

                # 4. Return Final Text to Client
                await websocket.send_text(agent_reply)

        except WebSocketDisconnect:
            print("Client disconnected")
        except Exception as e:
            print(f"Connection error: {e}")
            await websocket.close()