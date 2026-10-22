# VoiceCart 2.0

A voice-driven, agentic e-commerce platform. Users speak naturally to search for products, manage a cart, and place orders; a speech pipeline and a LangGraph-based multi-agent backend handle the rest.

> **Status:** active development. The full voice loop works end to end (speech in, agent, speech out), but there are known gaps, such as a stock race at checkout: see [Project Status](#project-status).

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
- [Shopper profile](#shopper-profile)
- [Spoken replies (TTS)](#spoken-replies-tts)
- [Evaluating the agent](#evaluating-the-agent)
- [Tests](#tests)
- [Project Status](#project-status)
- [Demo](#demo)
- [License](#license)

## Overview

VoiceCart lets a user speak a request ("do you have Amul butter?", "add two to my cart", "what's in my cart?"), either by holding a record button or hands-free, and get the answer back as text, product photo cards and a spoken reply. The request is routed to the right agent and executed, as the logged-in user, against a Postgres-backed product catalog.

The system is split into independent services that communicate over HTTP/WebSocket, so each piece (speech-to-text, agent orchestration, the commerce API) can be developed, deployed, and scaled separately.

## Architecture

```
                 audio / text / cards / speech (WebSocket)
┌──────────────┐ ◄──────────────────────────────────────► ┌─────────────┐
│   Frontend   │                                          │   Manager   │
│ (React/Vite) │                                          │  (Gateway)  │
└──────────────┘                                          └──────┬──────┘
                          ┌──────────────────┬────────────────────┤
                          ▼                  ▼                    ▼
                   ┌─────────────┐    ┌─────────────┐      ┌─────────────┐
                   │ STT Service │    │ TTS Service │      │    Agent    │
                   │   (Gnani)   │    │   (Gnani)   │      │ (LangGraph) │
                   └─────────────┘    └─────────────┘      └──────┬──────┘
                                                    ┌─────────────┼───────────────┐
                                                    ▼             ▼               ▼
                                             ┌───────────┐ ┌─────────────┐ ┌───────────┐
                                             │MCP Server │ │   Memory    │ │ Postgres  │
                                             └─────┬─────┘ │  (Chroma)   │ │ (agent    │
                                                   │ REST  └─────────────┘ │  state)   │
                                                   ▼ (user's JWT)          └───────────┘
                                             ┌─────────────┐
                                             │  Product    │──────► PostgreSQL
                                             │  Service    │
                                             └─────────────┘
```

1. The **frontend** records microphone audio in the browser (press-to-record, or hands-free with voice activity detection) and streams it over a WebSocket.
2. The **manager** buffers incoming audio chunks, and on an `END` signal forwards the complete clip to the **STT service**.
3. The **STT service** converts WebM/Opus audio to WAV (via `ffmpeg`) and transcribes it with the Gnani speech-to-text API.
4. The manager sends the transcript, with the user's JWT (passed by the frontend as `?token=` on the WebSocket URL) and the chat session id, to the **agent service**. It runs a LangGraph supervisor that routes each request to one or more specialists: `product`, `cart`, `order`, `review`, `recipe` (TheMealDB) and `shopping_list`. The shopping list agent turns a recipe or goal into catalog matches and adds them to the cart once the user confirms.
5. The specialists' tools come from the **MCP server** (`mcp_server/`), which turns each Product Service route into an MCP tool and forwards the user's JWT, so every action runs as the logged-in user.
6. The final reply, with any product photo cards, is sent back to the frontend over the same WebSocket.
7. If the **TTS service** is running, the manager also sends the reply to it (Gnani text-to-speech, using the same `GNANI_API_KEY` as STT) and follows the text with an `audio` message that the browser plays. The shopper can switch "Speak replies" off, and hands-free listening pauses while a reply is spoken. If TTS is down or unset, replies are simply text.

The pipeline is sequential (record, transcribe, agent, speak), and the agent is the slowest stage: a turn typically makes about four model calls.

The **Product Service** (the commerce backend) also exposes a standalone REST API (`/user`, `/product`, `/cart`, `/orders`, `/search`, `/reviews`, `/categories`, `/chat`, `/memories`, `/profile`) that the frontend uses directly for non-voice pages.

## Features

- **Voice shopping** - press-to-record, or a **hands-free** switch that keeps the microphone open and uses voice activity detection (`frontend/src/lib/speechDetector.ts`, an energy-based detector, not a trained model) to start recording when you speak and send the clip after about a second of silence. It adapts to background noise and ignores short clicks.
- **Spoken replies** - the assistant's answers are read aloud with Gnani text-to-speech; a "Speak replies" switch turns it off, and hands-free listening pauses while a reply plays.
- **Multi-agent orchestration** - a LangGraph supervisor routes each request to specialists for products, cart, orders, reviews, recipes and shopping lists, all calling tools over MCP as the logged-in user.
- **Product photo cards** - when the agent finds products, the reply carries photo cards for the screen.
- **Long-term memory** - an optional service remembers durable facts a shopper has said ("I'm vegetarian") and feeds them back, kept strictly per shopper.
- **Shopper profile** - age, preferences and medical conditions that the shopper enters themselves, passed to the agents at the start of each conversation.
- **Full commerce REST API** - users, products (with categories, images, reviews), cart, orders and chat sessions, built on FastAPI + SQLAlchemy + PostgreSQL.
- **React frontend** - voice first, so four pages behind a login: **Voice** (the conversation, with photo cards), a read-only **Catalogue** (photo grid with search, category and sort), **Orders** (history with item photos) and **Profile** (view, then Edit). Built with Vite, TypeScript, Tailwind (navy and violet theme) and shadcn/ui. Older demo pages are archived in `frontend/_removed/`.
- **Pluggable LLMs** - the agents run on any OpenAI-compatible chat endpoint, configured in `agent/.env`.
- **Observability and evals** - a local per-turn trace, optional LangSmith tracing, and a 15-conversation evaluation you can run against the live agent.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router, TanStack Query, Vitest |
| API Gateway | FastAPI, WebSockets, httpx |
| Speech-to-Text | Gnani STT API (`gnani-vachana` SDK), ffmpeg |
| Text-to-Speech | Gnani TTS API (`timbre-v2.5`) |
| Agent Orchestration | LangGraph, LangChain, MCP (`langchain-mcp-adapters`), OpenAI-compatible LLM endpoint |
| Long-term memory | Chroma (persistent, single process), FastAPI |
| Product Service | FastAPI, SQLAlchemy, Pydantic, JWT (`python-jose`), Passlib |
| Database | PostgreSQL (products, orders, chat transcripts, profiles, and the agent's conversation state) |
| Auth | OAuth2 / JWT (`oauth2.py`), bcrypt password hashing |
| Tracing | Local trace file, optional LangSmith |

## Project Structure

```
VoiceCart-2.0/
├── manager/                  # WebSocket gateway: audio -> STT -> agent -> TTS -> client
│   └── main.py
├── STT/                      # Speech-to-text microservice (Gnani)
│   └── stt_new.py
├── TTS/                      # Text-to-speech microservice (Gnani); POST /speak -> audio/wav
│   ├── tts_service.py
│   └── speech_text.py        # Cleans a reply for speaking (rupees, units, no markdown/emoji)
├── agent/                    # LangGraph agent service (POST /agent/{user_id})
│   ├── main.py               # FastAPI wrapper; loads MCP tools per request with the user's JWT
│   ├── graph.py              # Wires the nodes: START -> memory -> supervisor <-> specialists -> END
│   ├── nodes/                # One module per graph node
│   │   ├── memory.py         # First node: fetches the shopper's long-term memories
│   │   ├── supervisor.py     # Routing node (structured output)
│   │   ├── product.py  cart.py  order.py  review.py  recipe.py   # Tool-calling specialists: prompt + MCP tool allow-list
│   │   ├── shopping_list.py  # Builds, confirms and adds shopping lists
│   │   └── base.py           # The tool-calling loop the specialists share
│   ├── prompts.py            # Prompt pieces shared by several nodes (voice rules, memory and profile blocks)
│   ├── memory_client.py  profile_client.py   # Read memories / the profile for the verified shopper
│   └── cards.py  state.py  trace.py  llm.py  loop.py
├── mcp_server/               # MCP server: every tool the agents can call (store, recipes, show_products)
│   └── server.py
├── longterm_memory/          # Optional memory service: judges what to remember, stores it in Chroma, serves it per shopper
├── Product Service/          # The commerce backend (FastAPI)
│   └── app/
│       ├── main.py           # FastAPI app + router registration
│       ├── models.py         # SQLAlchemy models (users, products, cart, orders, reviews, chat, profiles...)
│       ├── schemas.py        # Pydantic schemas
│       ├── migrations.py     # Idempotent schema changes that create_all cannot make
│       ├── database.py  config.py  oauth2.py
│       ├── routers/          # user, product, cart, orders, search, reviews, categories, chat, memories, profile
│       └── utils/
├── frontend/                 # React app (Vite)
│   └── src/
│       ├── pages/            # Voice, Catalogue, Orders, Profile, Auth
│       ├── components/       # Conversation, ProductCard, RecordButton, ui/*
│       ├── hooks/            # useWebSocket, useHandsFree, useSpeech, useVoiceRecorder
│       ├── lib/              # api client, speechDetector (VAD), message parsing, catalogue helpers
│       └── contexts/         # AuthContext
├── evals/                    # 15-conversation evaluation of the live agent
├── docs/                     # SPEC.md
├── run-all.ps1               # Starts every service (Windows)
├── requirements.txt          # Combined Python dependencies (root)
└── LICENSE                   # GPL-3.0
```

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ (or Bun, given `bun.lockb` is present)
- PostgreSQL
- `ffmpeg` on your `PATH` (required by the STT service)
- A Gnani API key and the Gnani SDK (`gnani-vachana`) for speech in and out
- An OpenAI-compatible LLM endpoint (base URL, API key, model) for the agent service
- Optional: `chromadb` for long-term memory (large; never installed automatically)

### Clone

```bash
git clone https://github.com/Chiranjit680/VoiceCart-2.0.git
cd VoiceCart-2.0
```

### Install Python dependencies

On Windows `run-all.ps1` creates `.venv` and installs what is missing (see below). To do it by hand, install the per-service requirement files into one virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r "Product Service/requirements.txt" -r agent/requirements.txt -r mcp_server/requirements.txt \
            -r manager/requirements.txt -r STT/requirements.txt -r TTS/requirements.txt
```

`gnani-vachana` (the Gnani SDK) and `chromadb` are not installed by the script: install them yourself if you want speech and memory.

### Install frontend dependencies

```bash
cd frontend
npm install   # or: bun install
```

## Environment Variables

Secrets live in git-ignored `.env` files. Never commit them.

The root `.env` is read by the Product Service (and shared with the memory service and the agent):

```env
# Product Service / database
secret_key=
algorithm=
access_token_expire_minutes=
database_url=
database_hostname=
database_port=
database_username=
database_password=
database_name=
GEMINI_API_KEY=            # still required by the Product Service's settings, but nothing uses it any more

# Long-term memory (optional): a shared secret for the memory service
MEMORY_SERVICE_KEY=
# CHAT_RESUME_MINUTES / CHAT_IDLE_MINUTES / CHAT_RETENTION_DAYS tune chat sessions (see Conversations and sessions)
```

`STT/.env` holds the Gnani key, which the TTS service reuses (or give `TTS/.env` its own):

```env
GNANI_API_KEY=
# GNANI_LANGUAGE_CODE=en-IN
```

TTS options (all optional): `TTS_VOICE` (default `Pranav`), `TTS_MODEL` (`timbre-v2.5`), `TTS_LANGUAGE` (`en-IN`), `TTS_SPEED`, `TTS_TIMEOUT` (20 s).

`manager/.env` holds the manager's service URLs:

```env
STT_SERVICE_URL=http://localhost:8001/transcribe
TTS_SERVICE_URL=http://localhost:8006/speak   # optional; leave out to turn spoken replies off
AGENT_BASE_URL=http://localhost:8002
PRODUCT_SERVICE_URL=http://localhost:8000
```

`agent/.env` configures the LLM that drives the agents (any OpenAI-compatible endpoint), the MCP server URL and tracing; see `agent/.env.example`:

```env
INFERENCE_BASE_URL=
INFERENCE_API_KEY=
INFERENCE_MODEL=
MCP_SERVER_URL=http://127.0.0.1:8004/mcp
PRODUCT_SERVICE_URL=http://localhost:8000
# AGENT_DATABASE_URL=postgresql://...   # optional; defaults to database_url from the root .env
# LANGSMITH_TRACING=true  LANGSMITH_API_KEY=...  (see LangSmith tracing)
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

The STT and TTS services need the Gnani SDK (`gnani-vachana`), and STT also needs `ffmpeg` on PATH. Install the SDK into the venv yourself; until then the script skips them with a hint. TTS is optional: without it replies are text only.

Each service can also be run on its own. Typical local ports:

| Service | Command | Port |
|---|---|---|
| Product Service (REST API) | `uvicorn app.main:app --reload` (from `Product Service/`) | 8000 |
| STT service | `python STT/stt_new.py` | 8001 |
| TTS service (optional) | `uvicorn tts_service:app --port 8006` (from `TTS/`) | 8006 |
| MCP server | `MCP_TRANSPORT=streamable-http python mcp_server/server.py` | 8004 |
| Memory service (optional) | `uvicorn longterm_memory.api:create_app --factory --host 127.0.0.1 --port 8005` | 8005 |
| Agent service | `uvicorn agent.main:app --port 8002 --loop agent.loop:selector_loop_factory` (from the repo root) | 8002 |
| Manager (WebSocket gateway) | `uvicorn main:app --reload --port 8003` (from `manager/`) | 8003 |
| Frontend | `npm run dev` (from `frontend/`) | 8080 |

Start the Product Service, STT, MCP server and agent first (and TTS and the memory service if you want them), then the manager (which depends on STT and the agent), then the frontend. Log in on the frontend before using the voice console. The Voice page then connects to the manager's `/ws` endpoint by itself, using the user's token, and reconnects automatically if the link drops; the manager refuses connections without a valid token. The agent's `--loop` option is needed on Windows because its Postgres driver cannot run on uvicorn's default event loop.

## API Overview

The Product Service exposes the following routers, all mounted in `Product Service/app/main.py`:

| Router | Prefix | Purpose |
|---|---|---|
| `user` | `/user` | Registration, auth |
| `product` | `/product` | Product CRUD, listing |
| `cart` | `/cart` | Add/remove/view cart items |
| `orders` | `/orders` | Checkout, order history |
| `search` | `/search` | Product search/filtering |
| `reviews` | `/reviews` | Product reviews and ratings |
| `categories` | `/categories` | Category hierarchy |
| `chat` | `/chat` | Voice conversation sessions and transcripts |
| `memories` | `/memories` | The shopper's own long-term memories (list, delete) |
| `profile` | `/profile` | The shopper's own profile (get, replace) |

The agent service exposes a single endpoint, `POST /agent/{user_id}`, accepting `{"msg": "..."}` with an `Authorization: Bearer <jwt>` header and returning `{"response": "...", "products": [product cards to show]}`. The request must also carry an `X-Session-Id` header (see below), and the agent checks with the Product Service that the caller owns that session before answering.

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
- The `memory` node uses the verified shopper id that the request handler puts in the run's config. The shopper's profile is fetched once per conversation by the request handler and kept in the state.
- Tests (from the repo root): `python -m agent.test_graph`, `python -m agent.test_nodes`, `python -m agent.test_memory_client` and `python mcp_server/test_server.py`.

### Agent trace

Every turn is traced to the agent's console and to `agent/logs/trace.log` (rotated, git-ignored). For each model call it records exactly what the agent was sent (the system prompt, the last-20-message history, tool results) and what it answered (text or tool calls, token counts and timing), plus the supervisor's routing decisions and the final reply and product cards sent to the user. The trace contains conversations and tool output, so treat it as private. Set `AGENT_TRACE=off` in `agent/.env` to turn it off, or `AGENT_TRACE_MAX_CHARS=n` (default 3000) to shorten long messages.

### LangSmith tracing

With `LANGSMITH_TRACING=true` in `agent/.env` (plus `LANGSMITH_API_KEY`, and optionally `LANGSMITH_PROJECT` and `LANGSMITH_ENDPOINT`; see `agent/.env.example`), every turn is sent to LangSmith as one trace named `voicecart_turn`. Inside it are the memory node, each supervisor decision, the specialist that ran, and every model call and tool call it made, nested under the node that made them. The trace carries the session as its `thread_id` (so a conversation shows as a LangSmith thread), the turn number and the shopper's id. Set `LANGSMITH_TRACING=false` to turn it off.

- **The trace contains the conversation and the tool output** (product data, cart and order contents, delivery addresses, memories), and it is sent to LangSmith. LangSmith can hide inputs and outputs (`LANGSMITH_HIDE_INPUTS=true`, `LANGSMITH_HIDE_OUTPUTS=true`), which also hides what you would want to debug with.
- The specialists run their tool loop in `agent/nodes/base.py` rather than with a ready-made agent. That is so the run's config reaches every model and tool call: on Python 3.10 async code does not inherit it, and otherwise each specialist's model calls show up as separate, unconnected traces.
- This is separate from the local trace above, and both can be on at once.

### Long-term memory

The assistant can remember things a shopper has said across conversations ("I'm vegetarian", "I only buy Amul"). It is optional: without it, conversations work exactly as before.

- **Finding memories.** The memory service (`longterm_memory/`) runs a background loop over `chat_turns` rows where `checked = false`. For each thing the shopper said, a model (the one in `agent/.env`) decides whether it is durable personal information. If so, one short sentence is saved to Chroma and the row gets `longterm = true`; every row it has looked at gets `checked = true`. Assistant replies are never memories. A turn the model fails on stays unchecked and is retried. The two columns are added to `chat_turns` by the Product Service when it starts.
- **Keeping shoppers apart.** Every memory is tagged with its shopper, and all reading and writing goes through one class, `longterm_memory/user_memory.py`, bound to a single shopper. It always filters by that shopper, prefixes each memory's id with the shopper's id, and drops anything that is not theirs. The shopper's id comes from the database (when saving) or from the Product Service's verified login (when the agent reads); the `{user_id}` in the agent's URL is never used for it.
- **One process owns Chroma.** A persistent Chroma folder belongs to one process, so the memory service is the only one that opens it (`LONGTERM_MEMORY_DIR`, default `longterm_memory/chroma_data/`, git-ignored). The agent and the Product Service reach memories over HTTP with a shared secret.
- **Using memories.** At the start of each turn the agent asks the service for the shopper's five most relevant memories and gives them to the supervisor and the specialist agents as background, labelled as the shopper's own words, never as instructions or as a source of prices or permissions. If the service is off or slow, the turn simply has no memories.
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

## Shopper profile

The **Profile** page shows what a shopper has told us about themselves (age, preferences, medical conditions) and has an **Edit** button that opens a form to change it.

- **Storage.** One row per shopper in the `user_profiles` table (`user_id` primary key with a cascading foreign key to `users`; `age`; `preferences` and `medical_conditions` as JSON lists of short strings; `updated_at`). It is a separate table because it holds health information. The table is created when the Product Service starts. Values are stored as plain text, not encrypted.
- **API.** `GET /profile` and `PUT /profile` work on the logged-in shopper's own row and take no user id, so there is no way to name another shopper. `GET` returns an empty profile (not a 404) until something is saved; `PUT` replaces the whole profile. Age must be 0 to 120, entries are trimmed and de-duplicated, at most 80 characters each and 30 per list.
- **Use by the agent.** On the first turn of a conversation the agent fetches the profile with the shopper's own token and keeps it in the conversation state. The supervisor and the specialists see it as background about the shopper, never as instructions or a source of prices or permissions; medical conditions are used only to avoid unsuitable suggestions, and the assistant gives no medical advice. A profile edit applies from the next conversation. The profile goes to the inference model and, if LangSmith tracing is on, appears in those traces. It is not sent to the memory service.

## Spoken replies (TTS)

The TTS service (`TTS/`, port 8006) turns a reply into audio with Gnani text-to-speech. It is optional: without it, replies are text only.

- `POST /speak {"text": "..."}` returns `audio/wav` (or `204` when there is nothing speakable). The text is first cleaned for speech by `speech_text.py`: prices become "285 rupees", units are spelled out ("500 grams"), and markdown, links and emoji are dropped.
- The manager calls it after sending the reply text and then sends an `audio` message `{"type": "audio", "mime": "audio/wav", "data": "<base64>"}`. If TTS is down or slow, only the voice is lost.
- It uses `GNANI_API_KEY` from `TTS/.env` or `STT/.env`. The SDK's default model (`timbre-v2.0`) is retired by Gnani, so the service defaults to `timbre-v2.5`.
- In the browser, `useSpeech` plays the audio, a new reply replaces one still playing, speaking again stops it, and the "Speak replies" choice is remembered on that device. Hands-free listening is paused while audio plays so the microphone does not hear the speaker.

## Evaluating the agent

`evals/` holds a 15-conversation evaluation that runs against the **live** agent. Start the services first, then, from the repo root:

```bash
.venv/Scripts/python.exe -m evals.run_eval                     # all 15
.venv/Scripts/python.exe -m evals.run_eval --only checkout,recipe
.venv/Scripts/python.exe -m evals.run_eval --no-judge          # skip the model-judged rubric
```

- Each conversation registers its own throwaway shopper, so carts and orders never touch real users or each other.
- Each turn is checked in code: reply text patterns, number of product cards, and the **real** cart and order state read back from the Product Service (so "added" in a reply with an empty cart fails). Every reply also has to follow the voice rules (short, no markdown or emoji, no dollars).
- Judgement calls (did it invent a product, did it ask which dal) are listed as rubric lines and graded by the same model from the transcript.
- The 15 cover search, price, add, cart total, remove, an ambiguous item, over-stock, an unknown product, checkout, empty order history, recipes, shopping lists, reviews, follow-up references and off-topic or pressure messages. They rely on the seeded catalogue's names and prices.
- Results are printed and saved to `evals/results/` (git-ignored). The exit code is 0 only if every conversation passes. The agent is not deterministic, so scores vary from run to run; run it a few times before drawing conclusions.
- `python -m evals.test_checks` tests the scoring code alone, with no services.

## Tests

From the repo root (no services needed unless noted):

| What | Command |
|---|---|
| Agent graph, nodes, memory client, profile | `python -m agent.test_graph`, `python -m agent.test_nodes`, `python -m agent.test_memory_client`, `python -m agent.test_profile` |
| MCP server | `python mcp_server/test_server.py` |
| Product Service routes | `python "Product Service/test_memories_routes.py"`, `python "Product Service/test_profile_routes.py"` |
| Long-term memory | `python -m longterm_memory.test_memory`, `.test_user_memory`, `.test_api` (the Chroma ones skip if Chroma is missing) |
| TTS | `python test_tts.py` (from `TTS/`) |
| Eval scoring | `python -m evals.test_checks` |
| Frontend | `npx vitest run` (from `frontend/`; on a low-memory machine add `--pool=forks --poolOptions.forks.singleFork`) |

## Project Status

Under active development. What works: the whole voice loop, the six specialists over MCP, product photo cards, spoken replies, the Catalogue, Orders and Profile pages, per-shopper memory and the profile as agent context. Known gaps:

- **Stock race at checkout.** Checkout reads stock, checks it, then subtracts in Python without a row lock, so two shoppers buying the last units at the same moment can both succeed. Add-to-cart also checks only the quantity being added, not what is already in the cart, and a double-submitted checkout can create two orders. The fix is an atomic `UPDATE ... WHERE stock >= qty` plus locking the cart rows; it is not done yet.
- **Latency.** The pipeline is strictly sequential (record, transcribe, agent, speak) and a turn makes about four model calls (median agent time about 5 s in the trace). Ideas: skip the second supervisor call, route obvious requests without a model, stream TTS by sentence, stream STT.
- **Voice activity detection is energy-based**, so loud non-speech noise can trigger it; a neural VAD (for example Silero) would be more robust.
- **Capacity.** The agent's conversation-state pool allows 5 connections, and the agent rebuilds its MCP client and graph on every request.
- **Seed data.** Many catalogue products are placeholders without photos, so the Catalogue lists photographed products first.
- **Profile is plain text** in the database and is read once per conversation.
- **Windows-centric tooling.** `run-all.ps1` is PowerShell only.
- `GEMINI_API_KEY` is still a required Product Service setting even though nothing uses it.

## Demo

<p align="center">
  <a href="https://youtu.be/BUmCrM3Syqk">
    <img src="https://img.youtube.com/vi/BUmCrM3Syqk/maxresdefault.jpg"
         alt="VoiceCart Demo"
         width="800">
  </a>
</p>

## License

Licensed under the [GNU General Public License v3.0](LICENSE).
