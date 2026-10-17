# VoiceCart 2.0

A voice-driven, agentic e-commerce platform. Users speak naturally to search for products, manage a cart, and place orders; a speech pipeline and a LangGraph-based multi-agent backend handle the rest.

> **Status:** active development / work in progress. Some pieces (notably the frontend's REST integration) are stubbed out — see [Project Status](#project-status).

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running the Services](#running-the-services)
- [API Overview](#api-overview)
- [Project Status](#project-status)
- [Demo](#demo)
- [License](#license)

## Overview

VoiceCart lets a user hold down a record button, speak a request ("find me a gaming laptop under $1500", "add that to my cart", "what's in my cart?"), and get a spoken/text response back, with the underlying intent routed to the right agent and executed against a Postgres-backed product catalog.

The system is split into independent services that communicate over HTTP/WebSocket, so each piece (speech-to-text, agent orchestration, the commerce API) can be developed, deployed, and scaled separately.

## Architecture

```
┌──────────────┐   audio (WS)   ┌─────────────┐   HTTP    ┌─────────────┐
│   Frontend   │ ─────────────► │   Manager   │ ────────► │ STT Service │
│ (React/Vite) │ ◄───────────── │  (Gateway)  │ ◄──────── │  (Whisper)  │
└──────────────┘   text (WS)    └─────────────┘  text     └─────────────┘
                                        │
                                        │ HTTP (transcript)
                                        ▼
                                 ┌─────────────┐
                                 │   Agent     │
                                 │ (LangGraph) │
                                 └─────────────┘
                                        │
                                        │ MCP (streamable HTTP, user's JWT)
                                        ▼
                                 ┌─────────────┐
                                 │ MCP Server  │
                                 └─────────────┘
                                        │
                                        │ HTTP (REST)
                                        ▼
                                 ┌─────────────┐
                                 │   Backend   │
                                 │  (FastAPI   │
                                 │   REST API) │
                                 └─────────────┘
                                        │
                                        ▼
                                 ┌─────────────┐
                                 │  PostgreSQL │
                                 └─────────────┘
```

1. The **frontend** records microphone audio in the browser and streams it over a WebSocket.
2. The **manager** buffers incoming audio chunks, and on an `END` signal forwards the complete clip to the **STT service**.
3. The **STT service** converts WebM/Opus audio to WAV (via `ffmpeg`) and transcribes it with `faster-whisper`.
4. The manager sends the transcript, with the user's JWT (passed by the frontend as `?token=` on the WebSocket URL), to the **agent service**. It runs a LangGraph supervisor that routes each request to one or more subagents: `product`, `cart`, `order`, `review`, `recipe` (TheMealDB) and `shopping_list`. The shopping list agent turns a recipe or goal into catalog matches and adds them to the cart once the user confirms.
5. The subagents' tools come from the **MCP server** (`mcp_server/`), which turns each backend route into an MCP tool and forwards the user's JWT, so every action runs as the logged-in user.
6. The final reply is streamed back to the frontend over the same WebSocket.

The **backend** also exposes a standalone REST API (`/user`, `/product`, `/cart`, `/orders`, `/search`, `/reviews`, `/categories`) for non-voice, direct frontend use.

## Features

- **Voice shopping** — press-to-record UI, streamed to a speech-to-text pipeline and a conversational agent. A **hands-free** switch on the Voice page keeps the microphone open and uses voice activity detection (`frontend/src/lib/speechDetector.ts`) to start recording when you speak and send the clip after about a second of silence; it adapts to background noise and ignores short clicks.
- **Multi-agent orchestration** — a LangGraph router dispatches requests to a shopping/search agent or a cart/checkout agent, with tool-calling against the product database.
- **Full commerce REST API** — users, products (with categories, images, reviews), cart, and orders, built on FastAPI + SQLAlchemy + PostgreSQL.
- **React frontend** — product browsing, search, categories, cart, order history, reviews, a voice console, and a crawler dashboard (currently demo data), built with Vite, TypeScript, Tailwind, and shadcn/ui.
- **Pluggable LLMs** — the agents run on any OpenAI-compatible chat endpoint, configured in `agent/.env`.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router, TanStack Query |
| API Gateway | FastAPI, WebSockets, httpx |
| Speech-to-Text | faster-whisper (`base.en`, int8 on CPU), ffmpeg |
| Agent Orchestration | LangGraph, LangChain, MCP (`langchain-mcp-adapters`), OpenAI-compatible LLM endpoint |
| Backend API | FastAPI, SQLAlchemy, Pydantic, JWT (`python-jose`), Passlib |
| Database | PostgreSQL |
| Auth | OAuth2 / JWT (`oauth2.py`), bcrypt password hashing |

## Project Structure

```
VoiceCart-2.0/
├── manager/                  # WebSocket gateway: audio → STT → agent → client
│   └── main.py
├── STT/                      # Speech-to-text microservice (faster-whisper)
│   └── stt_new.py
├── agent/                    # LangGraph agent service (POST /agent/{user_id})
│   ├── main.py               # FastAPI wrapper; loads MCP tools per request with the user's JWT
│   ├── graph.py              # Wires the nodes: START → memory → supervisor ⇄ specialists → END
│   ├── nodes/                # One module per graph node
│   │   ├── memory.py         # First node: fetches the shopper's long-term memories
│   │   ├── supervisor.py     # Routing node (structured output)
│   │   ├── product.py  cart.py  order.py  review.py  recipe.py   # Tool-calling specialists: prompt + MCP tool allow-list
│   │   ├── shopping_list.py  # Builds, confirms and adds shopping lists
│   │   └── base.py           # The tool-calling loop the specialists share
│   ├── prompts.py            # Prompt pieces shared by several nodes
│   ├── cards.py  state.py  trace.py  memory_client.py  llm.py
├── mcp_server/               # MCP server: every tool the agents can call (store, recipes, show_products)
│   └── server.py
├── packages/src/
│   ├── Backend/app/          # Core REST API
│   │   ├── main.py           # FastAPI app + router registration
│   │   ├── models.py         # SQLAlchemy models (users, products, cart, orders, reviews...)
│   │   ├── schemas.py        # Pydantic schemas
│   │   ├── database.py       # Engine / session setup
│   │   ├── config.py         # Settings (env-driven)
│   │   ├── oauth2.py         # JWT auth
│   │   ├── routers/          # user, product, cart, orders, search, reviews, categories
│   │   └── utils/            # hashing, filtering, product helpers
│   └── frontend/              # React app (Vite)
│       └── src/
│           ├── pages/          # Products, ProductDetail, Cart, Orders, Search, Categories, Reviews, Voice, Crawler, Auth
│           ├── components/     # RecordButton, ConnectionPanel, ActivityLog, MessageBox, ui/*
│           ├── hooks/          # useWebSocket, useVoiceRecorder
│           └── contexts/       # AuthContext
├── Demo/                      # Demo recording
├── requirements.txt           # Combined Python dependencies (root)
└── LICENSE                    # GPL-3.0
```

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ (or Bun, given `bun.lockb` is present)
- PostgreSQL
- `ffmpeg` on your `PATH` (required by the STT service)
- An OpenAI-compatible LLM endpoint (base URL, API key, model) for the agent service

### Clone

```bash
git clone https://github.com/Chiranjit680/VoiceCart-2.0.git
cd VoiceCart-2.0
```

### Install Python dependencies

Each service currently shares the root `requirements.txt` (a superset covering the backend, agent, and STT service). Installing into a single virtual environment is the simplest path:

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

The `manager` service has its own lightweight dependency set in `manager/requirements.txt` if you'd rather isolate it.

### Install frontend dependencies

```bash
cd packages/src/frontend
npm install   # or: bun install
```

## Environment Variables

Create a `.env` file at the repository root (used by the `Backend` config and referenced by the `manager` service) with:

```env
# Backend / database
secret_key=
algorithm=
access_token_expire_minutes=
database_url=
database_hostname=
database_port=
database_username=
database_password=
database_name=

# LLM
GEMINI_API_KEY=
```

`manager/.env` holds the manager's service URLs:

```env
STT_SERVICE_URL=http://localhost:8001/transcribe
AGENT_BASE_URL=http://localhost:8002
PRODUCT_SERVICE_URL=http://localhost:8000
```

`agent/.env` configures the LLM that drives the agents (any OpenAI-compatible endpoint) and the MCP server URL; see `agent/.env.example`:

```env
INFERENCE_BASE_URL=
INFERENCE_API_KEY=
INFERENCE_MODEL=
MCP_SERVER_URL=http://127.0.0.1:8004/mcp
PRODUCT_SERVICE_URL=http://localhost:8000
# AGENT_DATABASE_URL=postgresql://...   # optional; defaults to database_url from the root .env
```

`mcp_server/.env` (see `mcp_server/.env.example`) sets `PRODUCT_SERVICE_URL` and, for stdio use from an MCP client such as Claude Code, optional login credentials.

## Running the Services

On Windows, `run-all.ps1` starts every service in its own window, in dependency order, and reports which ports came up:

```powershell
.\run-all.ps1              # start everything (already-running services are skipped)
.\run-all.ps1 -Install     # force a reinstall of the Python + npm dependencies first
.\run-all.ps1 -NoFrontend  # backend services only
.\run-all.ps1 -Stop        # stop everything
```

It uses `.venv` or `venv` in the repo (creating `.venv` if neither exists) and installs the packages from each service's `requirements.txt` only when some are missing; pass `-Python <path>` to use another interpreter, which it will not install into. A service with missing packages is reported and skipped rather than crashing. Run `-Stop` before reinstalling, since Windows can't replace files a running service has open. The frontend uses port 8080, or 5173 if another program holds 8080. If PowerShell blocks the script, run it with `powershell -ExecutionPolicy Bypass -File .\run-all.ps1`.

The STT service also needs the Gnani STT SDK (`gnani.stt`), which isn't on PyPI under a name I could find, plus `ffmpeg` on PATH. Install the SDK into the venv yourself; until then the script skips STT and the voice page can't transcribe.

Each service can also be run on its own. Typical local ports:

| Service | Command | Port |
|---|---|---|
| Backend REST API | `uvicorn app.main:app --reload` (from `packages/src/Backend`) | 8000 |
| STT service | `python STT/stt.py` | 8001 |
| MCP server | `MCP_TRANSPORT=streamable-http python mcp_server/server.py` | 8004 |
| Memory service (optional) | `uvicorn longterm_memory.api:create_app --factory --host 127.0.0.1 --port 8005` | 8005 |
| Agent service | `uvicorn agent.main:app --port 8002 --loop agent.loop:selector_loop_factory` (from the repo root) | 8002 |
| Manager (WebSocket gateway) | `uvicorn main:app --reload --port 8003` (from `manager/`) | 8003 |
| Frontend | `npm run dev` (from `frontend/`) | 8080 |

Start the backend, STT, MCP server and agent first, then the manager (which depends on STT and the agent), then the frontend. Log in on the frontend before using the voice console. The Voice page then connects to the manager's `/ws` endpoint by itself, using the user's token, and reconnects automatically if the link drops; the manager refuses connections without a valid token. The agent's `--loop` option is needed on Windows because its Postgres driver cannot run on uvicorn's default event loop.

## API Overview

The backend exposes the following resource routers, all mounted on the root FastAPI app in `packages/src/Backend/app/main.py`:

| Router | Prefix | Purpose |
|---|---|---|
| `user` | `/user` | Registration, auth |
| `product` | `/product` | Product CRUD, listing |
| `cart` | `/cart` | Add/remove/view cart items |
| `orders` | `/orders` | Checkout, order history |
| `search` | `/search` | Product search/filtering |
| `reviews` | `/reviews` | Product reviews and ratings |
| `categories` | `/categories` | Category hierarchy |

The agent service exposes a single endpoint, `POST /agent/{user_id}`, accepting `{"msg": "..."}` with an `Authorization: Bearer <jwt>` header and returning `{"response": "..."}`. The request must also carry an `X-Session-Id` header (see below), and the agent checks with the Product Service that the caller owns that session before answering.

### Conversations and sessions

A **session** is one voice conversation: a single WebSocket connection, or a reconnect within `CHAT_RESUME_MINUTES` (default 10) of the last disconnect, so a network blip does not wipe the conversation. Two open tabs get two separate sessions.

- The manager opens a session when a client connects (`POST /chat/sessions/open`) and ends it on disconnect.
- The agent's working state (messages, a pending shopping list) is checkpointed in Postgres under the session id, so it survives agent restarts. The readable transcript, one row per message with the replying subagent, is stored in `chat_sessions` / `chat_turns` through the Product Service.
- Sessions with no activity for `CHAT_IDLE_MINUTES` (default 30) are closed, and sessions older than `CHAT_RETENTION_DAYS` (default 30, `0` disables) are deleted along with their agent state. Set these in the root `.env`.
- Users can list their sessions (`GET /chat/sessions`), read one with its transcript (`GET /chat/sessions/{id}`) and delete one (`DELETE /chat/sessions/{id}`).
- Only transcripts are stored: no audio and no login tokens. Spoken details such as addresses are stored as said.

### Agent graph

Each turn runs `START → memory → supervisor`, and the supervisor hands the request to one specialist at a time (`product`, `cart`, `order`, `review`, `recipe`, `shopping_list`). Each specialist reports back to the supervisor, which ends the turn when the request is handled. Every node is its own module in `agent/nodes/`.

- Every tool a specialist can call is served by the MCP server (`mcp_server/server.py`): the store tools, the recipe tools (TheMealDB) and `show_products`, which puts photo cards on the screen. The agent defines no tools of its own.
- Each specialist lists the MCP tools it may use in its own module. Admin, account and `create_order` tools are given to no agent, and a test fails if a new MCP tool is neither given to an agent nor deliberately withheld. If the MCP server lacks a tool an agent needs, the turn fails with the tool's name instead of the agent quietly working without it; restart the MCP server after adding tools.
- The `memory` node uses the verified shopper id that the request handler puts in the run's config.
- Tests (from the repo root): `python -m agent.test_graph`, `python -m agent.test_nodes`, `python -m agent.test_memory_client` and `python mcp_server/test_server.py`.

### Agent trace

Every turn is traced to the agent's console and to `agent/logs/trace.log` (rotated, git-ignored). For each model call it records exactly what the agent was sent (the system prompt, the last-20-message history, tool results) and what it answered (text or tool calls, token counts and timing), plus the supervisor's routing decisions and the final reply and product cards sent to the user. The trace contains conversations and tool output, so treat it as private. Set `AGENT_TRACE=off` in `agent/.env` to turn it off, or `AGENT_TRACE_MAX_CHARS=n` (default 3000) to shorten long messages.

### Long-term memory

The assistant can remember things a shopper has said across conversations ("I'm vegetarian", "I only buy Amul"). It is optional: without it, conversations work exactly as before.

- **Finding memories.** The memory service (`longterm_memory/`) runs a background loop over `chat_turns` rows where `checked = false`. For each thing the shopper said, a model (the one in `agent/.env`) decides whether it is durable personal information. If so, one short sentence is saved to Chroma and the row gets `longterm = true`; every row it has looked at gets `checked = true`. Assistant replies are never memories. A turn the model fails on stays unchecked and is retried. The two columns are added to `chat_turns` by the Product Service when it starts.
- **Keeping shoppers apart.** Every memory is tagged with its shopper, and all reading and writing goes through one class, `longterm_memory/user_memory.py`, bound to a single shopper. It always filters by that shopper, prefixes each memory's id with the shopper's id, and drops anything that is not theirs. The shopper's id comes from the database (when saving) or from the Product Service's verified login (when the agent reads); the `{user_id}` in the agent's URL is never used for it.
- **One process owns Chroma.** A persistent Chroma folder belongs to one process, so the memory service is the only one that opens it (`LONGTERM_MEMORY_DIR`, default `longterm_memory/chroma_data/`, git-ignored). The agent and the Product Service reach memories over HTTP with a shared secret.
- **Using memories.** At the start of each turn the agent asks the service for the shopper's five most relevant memories and gives them to the specialist agents as background, labelled as the shopper's own words, never as instructions or as a source of prices or permissions. If the service is off or slow, the turn simply has no memories.
- **Shopper controls.** `GET /memories`, `DELETE /memories/{id}` and `DELETE /memories` on the Product Service list, delete one, or forget all of the logged-in shopper's memories. Deleting a conversation does not delete what was learned from it.

Setup:

1. Install Chroma into the project venv (it is large and is never installed automatically): `.venv/Scripts/python.exe -m pip install -r longterm_memory/requirements.txt`. The first use also downloads a small embedding model.
2. Put a secret in the root `.env`: `MEMORY_SERVICE_KEY=<random>`. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. The Product Service, the agent and the memory service all read it from there. `MEMORY_SERVICE_URL` (default `http://127.0.0.1:8005`) is optional.
3. Start the Product Service once so it adds the columns, then run `run-all.ps1` (it starts the memory service when Chroma and the key are present, and skips it with a reason otherwise).

Useful commands, from the repo root:

- `python -m longterm_memory.memory --dry-run --limit 20` shows what the model would remember from unchecked turns, without saving or flagging anything (it needs neither Chroma nor the key).
- `python -m longterm_memory.memory --once` processes one batch. Tuning: `MEMORY_POLL_SECONDS` (60), `MEMORY_BATCH_SIZE` (20), `MEMORY_CONTEXT_TURNS` (4).
- Tests: `python -m longterm_memory.test_memory`, `python -m longterm_memory.test_user_memory`, `python -m longterm_memory.test_api`, `python -m agent.test_memory_client` and `python "Product Service/test_memories_routes.py"`. The ones that use real Chroma are skipped until it is installed.

Existing turns start as unchecked, so the first run goes through the whole backlog. The memory text is the shopper's own words processed by a model, so the Chroma folder contains personal data.

## Project Status

This project is under active, fast-moving development. Notable in-progress items:

- The frontend's `src/lib/api.ts` only implements login and registration — the other pages are not yet wired to the live backend REST API.
- The Crawler page in the frontend renders static demo data; there is no live crawler service yet.
- Open items tracked in `TODO.txt` include reorganizing the backend/frontend layout, moving STT processing fully in-memory, and extending the search schema.

## Demo

<p align="center">
  <a href="https://youtu.be/jr3y7Brf-hk">
    <img src="https://img.youtube.com/vi/jr3y7Brf-hk/maxresdefault.jpg"
         alt="VoiceCart Demo"
         width="800">
  </a>
</p>

## License

Licensed under the [GNU General Public License v3.0](LICENSE).
