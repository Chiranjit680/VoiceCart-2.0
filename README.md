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
                                        │ SQLAlchemy ORM
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
4. The manager sends the transcript to the **agent service**, which runs a LangGraph workflow (`router → shopping_list_agent | cart_agent`) backed by a local Ollama model or Gemini.
5. Agent tools query the **backend** REST API's database layer directly (SQLAlchemy models shared across the `Backend` and `agent` packages) to search products, manage carts, and place orders.
6. The final reply is streamed back to the frontend over the same WebSocket.

The **backend** also exposes a standalone REST API (`/user`, `/product`, `/cart`, `/orders`, `/search`, `/reviews`, `/categories`) for non-voice, direct frontend use.

## Features

- **Voice shopping** — press-to-record UI, streamed to a speech-to-text pipeline and a conversational agent.
- **Multi-agent orchestration** — a LangGraph router dispatches requests to a shopping/search agent or a cart/checkout agent, with tool-calling against the product database.
- **Full commerce REST API** — users, products (with categories, images, reviews), cart, and orders, built on FastAPI + SQLAlchemy + PostgreSQL.
- **React frontend** — product browsing, search, categories, cart, order history, reviews, a voice console, and a crawler dashboard (currently demo data), built with Vite, TypeScript, Tailwind, and shadcn/ui.
- **Pluggable LLMs** — the agent layer supports both a local Ollama model (`qwen2.5:3b`) and Google Gemini (`gemini-2.0-flash`).

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, React Router, TanStack Query |
| API Gateway | FastAPI, WebSockets, httpx |
| Speech-to-Text | faster-whisper (`base.en`, int8 on CPU), ffmpeg |
| Agent Orchestration | LangGraph, LangChain, Ollama, Google Gemini |
| Backend API | FastAPI, SQLAlchemy, Pydantic, JWT (`python-jose`), Passlib |
| Database | PostgreSQL |
| Auth | OAuth2 / JWT (`oauth2.py`), bcrypt password hashing |

## Project Structure

```
VoiceCart-2.0/
├── manager/                  # WebSocket gateway: audio → STT → agent → client
│   └── main.py
├── STT/                      # Speech-to-text microservice (faster-whisper)
│   └── stt.py
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
│   ├── agent/                 # LangGraph agent service
│   │   ├── main.py            # FastAPI wrapper (/agent/{user_id})
│   │   ├── agent_main.py      # Router + shopping/cart agent graph
│   │   ├── tools.py           # LangChain tools backed by Backend models
│   │   └── scrappable/        # Experimental/legacy agent implementations
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
- [Ollama](https://ollama.com) running locally with `qwen2.5:3b` pulled, and/or a Google Gemini API key

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

# Service URLs (used by the manager)
STT_SERVICE_URL=http://localhost:8001/transcribe
AGENT_SERVICE_URL=http://localhost:8002/agent/123
```

`manager/.env` mirrors the `STT_SERVICE_URL` / `AGENT_SERVICE_URL` pair for the manager service specifically.

## Running the Services

Each service runs independently. Typical local ports:

| Service | Command | Port |
|---|---|---|
| Backend REST API | `uvicorn app.main:app --reload` (from `packages/src/Backend`) | 8000 |
| STT service | `python STT/stt.py` | 8001 |
| Agent service | `python packages/src/agent/main.py` | 8002 |
| Manager (WebSocket gateway) | `uvicorn main:app --reload --port 8003` (from `manager/`) | 8003 |
| Frontend | `npm run dev` (from `packages/src/frontend`) | 5173 |

Start the backend, STT, and agent services first, then the manager (which depends on both), then the frontend. The frontend's voice console connects to the manager's `/ws` WebSocket endpoint.

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

The agent service exposes a single endpoint, `POST /agent/{user_id}`, accepting `{"msg": "..."}` and returning `{"response": "..."}`.

## Project Status

This project is under active, fast-moving development. Notable in-progress items:

- The frontend's `src/lib/api.ts` is currently a placeholder — most pages are not yet wired to the live backend REST API.
- The Crawler page in the frontend renders static demo data; there is no live crawler service yet.
- `packages/src/agent/scrappable/` contains earlier/experimental agent implementations kept for reference.
- Open items tracked in `TODO.txt` include reorganizing the backend/frontend layout, moving STT processing fully in-memory, and extending the search schema.

## Demo

A recorded walkthrough is available at `Demo/VoiceCart - Google Chrome 2026-02-07 13-44-20.mp4`.

## License

Licensed under the [GNU General Public License v3.0](LICENSE).
