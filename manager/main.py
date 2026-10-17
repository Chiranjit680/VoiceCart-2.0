import base64
import json
import os
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

STT_URL = os.getenv("STT_SERVICE_URL")
AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://localhost:8002").rstrip("/")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8000").rstrip("/")

# WebSocket close code meaning "log in again"; the frontend does not retry on it.
CLOSE_AUTH_FAILED = 4401

app = FastAPI()

# Messages to the browser: notices ("Please log in first...", "(no speech detected)") are plain text.
# The conversation itself is JSON:
#   {"type": "transcript", "text": "what the user said"}
#   {"type": "reply", "text": "what the assistant says", "products": [product cards with photos]}


def user_id_from_token(token: str):
    """Read the user_id claim from a JWT without verifying it.

    Only used to route the request to the agent; the Product Service verifies
    the token on every call (opening the chat session below, and every tool call).
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))["user_id"]
    except (IndexError, ValueError, KeyError):
        return None


async def open_session(token: str) -> str:
    """Start a chat session, or continue one that ended moments ago (decided by the Product Service)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{PRODUCT_SERVICE_URL}/chat/sessions/open", headers={"Authorization": f"Bearer {token}"}
        )
    response.raise_for_status()
    body = response.json()
    print(f"Chat session {body['id']} ({'resumed' if body['resumed'] else 'new'})")
    return body["id"]


async def end_session(token: str, session_id: str):
    """Mark the session ended. Best effort: the Product Service also closes idle sessions on its own."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{PRODUCT_SERVICE_URL}/chat/sessions/{session_id}/end",
                json={"reason": "disconnect"},
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception as e:
        print(f"Could not end chat session {session_id}: {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # The frontend connects with ws://.../ws?token=<jwt> so the agent can act as the logged-in user.
    token = websocket.query_params.get("token")
    user_id = user_id_from_token(token) if token else None
    if user_id is None:
        await websocket.send_text("Please log in first so I can help with your shopping.")
        await websocket.close(code=CLOSE_AUTH_FAILED)
        return

    try:
        session_id = await open_session(token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            await websocket.send_text("Your login has expired. Please log in again.")
            await websocket.close(code=CLOSE_AUTH_FAILED)
        else:
            await websocket.send_text("Sorry, I couldn't start the conversation. Please try again.")
            await websocket.close(code=1011)
        return
    except httpx.HTTPError as e:
        print(f"Product Service unreachable: {e}")
        await websocket.send_text("Sorry, the store is not reachable right now.")
        await websocket.close(code=1011)
        return

    agent_url = f"{AGENT_BASE_URL}/agent/{user_id}"
    agent_headers = {"Authorization": f"Bearer {token}", "X-Session-Id": session_id}

    # Agent turns can chain several LLM and tool calls, so allow more time than STT needs.
    async with httpx.AsyncClient(timeout=120.0) as client:
        audio_buffer = bytearray()  # accumulate WebM chunks here

        try:
            while True:
                # Receive either binary (audio chunk) or text ("END" signal)
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    print("Client disconnected")
                    break

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

                    # Show the user what was heard while the agent works on it
                    await websocket.send_text(json.dumps({"type": "transcript", "text": transcribed_text}))

                    # 2. Send Transcribed Text to Agent Service
                    try:
                        agent_response = await client.post(
                            agent_url,
                            json={"msg": transcribed_text},
                            headers=agent_headers,
                        )
                        agent_response.raise_for_status()
                        agent_body = agent_response.json()
                        agent_reply = agent_body.get("response", "")
                        agent_products = agent_body.get("products", [])
                        print(f"Agent Reply: {agent_reply} ({len(agent_products)} product card(s))")
                    except Exception as e:
                        print(f"Agent Error: {e}")
                        await websocket.send_text("Error connecting to agent.")
                        continue

                    # 3. Return the reply and the product cards to show with it
                    await websocket.send_text(json.dumps({"type": "reply", "text": agent_reply, "products": agent_products}))

        except WebSocketDisconnect:
            print("Client disconnected")
        except Exception as e:
            print(f"Connection error: {e}")
            try:
                await websocket.close()
            except Exception:
                pass
        finally:
            # Whatever ended the connection, close out the conversation.
            await end_session(token, session_id)

#port 8003
