import os
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

STT_URL = os.getenv("STT_SERVICE_URL")
AGENT_URL = os.getenv("AGENT_SERVICE_URL")

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        audio_buffer = bytearray()  # accumulate WebM chunks here
        
        try:
            while True:
                # Receive either binary (audio chunk) or text ("END" signal)
                message = await websocket.receive()
                
                if "bytes" in message:
                    # Binary frame → accumulate audio chunk
                    chunk = message["bytes"]
                    audio_buffer.extend(chunk)
                    print(f"Buffered chunk: {len(chunk)} bytes (total: {len(audio_buffer)} bytes)")
                    continue
                
                if "text" in message and message["text"] == "END":
                    # END signal → recording finished, process the complete audio
                    if len(audio_buffer) == 0:
                        await websocket.send_text("(no audio received)")
                        continue
                    
                    print(f"END received. Processing {len(audio_buffer)} bytes of audio...")
                    
                    # 1. Send complete audio to STT Service
                    try:
                        stt_response = await client.post(
                            STT_URL,
                            files={'file': ('audio.webm', bytes(audio_buffer), 'audio/webm')}
                        )
                        stt_response.raise_for_status()
                        transcribed_text = stt_response.json().get("text", "")
                        print(f"STT Transcript: {transcribed_text}")
                    except Exception as e:
                        print(f"STT Error: {e}")
                        await websocket.send_text("Error processing speech.")
                        audio_buffer.clear()
                        continue
                    
                    # Clear buffer for next recording session
                    audio_buffer.clear()
                    
                    if not transcribed_text.strip():
                        await websocket.send_text("(no speech detected)")
                        continue
                    
                    # 2. Send Transcribed Text to Agent Service
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
                    
                    # 3. Return Final Text to Client
                    await websocket.send_text(agent_reply)

        except WebSocketDisconnect:
            print("Client disconnected")
        except Exception as e:
            print(f"Connection error: {e}")
            await websocket.close()
            
#port 8003