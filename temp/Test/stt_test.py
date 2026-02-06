import asyncio
import websockets
import time

# 1. Configuration
URI = "ws://localhost:8000/ws/audio"
AUDIO_FILE = "test_audio.wav" # Make sure this file exists!

async def test_transcription():
    print(f"Connecting to {URI}...")
    async with websockets.connect(URI) as websocket:
        print("Connected. Sending audio...")
        
        # 2. Read audio file into memory
        with open(AUDIO_FILE, "rb") as f:
            audio_data = f.read()
        
        # 3. Start timer for latency check
        start_time = time.time()
        
        # 4. Send the audio bytes
        await websocket.send(audio_data)
        
        # 5. Wait for response
        response = await websocket.recv()
        end_time = time.time()
        
        print("\n--- Result ---")
        print(f"Server Response: {response}")
        print(f"Total Latency: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    asyncio.run(test_transcription())