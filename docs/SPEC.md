# VoiceCart 2.0: Requirements & Architecture

*Status: draft v1 · 16 Oct 2026 · Target: Gnani AI internship submission (due in about a week)*

---

## 1. Goal

VoiceCart 2.0 is a voice shopping assistant you talk to naturally, the way you would on a phone call. You speak in English, Hindi or Hinglish. It searches the catalogue, manages your cart and places orders through real tool calls, and replies in a natural voice. You can interrupt it mid-sentence.

The submission should show three things:

1. **Gnani speech done properly.** Use streaming STT and streaming TTS with barge-in, rather than calling an API on a recorded file.
2. **A real agent.** Multi-agent routing, reliable tool calling, memory across turns and sessions, and safe handling of anything that changes your cart or orders.
3. **Engineering discipline.** A latency budget and how it was measured, an eval script, and a clean repo.

## 2. Where the code is today

| Area | Current state | Gap |
|---|---|---|
| Frontend | React/Vite/shadcn app. The voice page records a single WebM blob, sends it over WebSocket after you release the button, and shows text replies. `lib/api.ts` is a placeholder. | Push-to-talk only. No audio playback, no live transcript, the cart doesn't update after voice actions, and no JWT is sent on the voice path. |
| `manager/` | WebSocket gateway: buffers audio → STT → `POST AGENT_SERVICE_URL`. | **It doesn't forward `Authorization`, but the agent requires it, so every voice turn currently gets "Please log in first."** It also hard-codes user `123` in the URL. |
| `STT/stt_new.py` | Gnani REST STT on a temp WAV converted with ffmpeg. | File-based with temp files on disk. No streaming, no VAD, no interim results. |
| `agent/` | LangGraph supervisor → 6 specialists (product, cart, order, review, recipe, shopping_list), tools loaded from MCP, `InMemorySaver`, `thread_id = user_id`. The LLM is `deepseek-v4-flash` via an OpenAI-compatible endpoint. | Not streamed. 3+ sequential LLM calls per turn (supervisor → specialist → supervisor FINISH). Graph and MCP client are rebuilt on every request. Memory is lost on restart, and there's one endless thread per user with no session concept. Checkout, clear-cart and cancel have no confirmation step. |
| `mcp_server/` | FastMCP wrapper over every Product Service route; forwards the caller's JWT. | Good base. Tool outputs are verbose (full product rows), and mutating calls have no idempotency. |
| `Product Service/` | FastAPI + SQLAlchemy + Postgres: users, products, categories, cart, orders, reviews. Search ranks results with weighted `ILIKE`. | Keyword search won't match Hinglish or Hindi terms ("doodh", "aloo", "do kilo chawal"). Prices are in `$`. `config.py` requires an unused `GEMINI_API_KEY`. There's a space in the folder name. |
| Repo | | The README describes the deleted `packages/src` layout. The root `requirements.txt` is a large superset. No docker-compose. |

## 3. Decisions made

| # | Decision | Choice |
|---|---|---|
| D1 | Conversation mode | **Full-duplex streaming with barge-in.** |
| D2 | Voice framework | **Pipecat** with the official `pipecat-gnani` plugin (Gnani WebSocket STT + Gnani WebSocket TTS). |
| D3 | LLM | **Inference-provider API** (the current OpenAI-compatible endpoint, `deepseek-v4-flash`), swappable through env vars. Gnani has no public LLM API. |
| D4 | Agent runtime | **Keep LangGraph** as its own service behind a streaming API. Pipecat handles audio and LangGraph handles reasoning. |
| D5 | Tool layer | **Keep the MCP server** as the single gateway to the Product Service. |
| D6 | Languages | **English (en-IN), Hindi (hi-IN), Hinglish code-mix.** The bot replies in the user's language. |
| D7 | Persistence | Postgres for everything: commerce data, LangGraph checkpoints, sessions and long-term memory. No new database. |
| D8 | Currency | Switch to **INR (₹)**, spoken as "rupees". |

## 4. Requirements

Priority: **P0** = must be in the submission · **P1** = do if time allows this week · **P2** = later.

### 4.1 Functional

**Voice I/O**

| ID | Requirement | Pri |
|---|---|---|
| V1 | User starts a voice session from the browser. Audio streams continuously and there is no record button. | P0 |
| V2 | End-of-turn is detected automatically with VAD. The user doesn't press anything to finish speaking. | P0 |
| V3 | Gnani streaming STT, with interim transcripts shown live and the final transcript sent to the agent. | P0 |
| V4 | Replies are spoken with Gnani streaming TTS. Audio starts before the full reply has been generated (sentence-level streaming). | P0 |
| V5 | **Barge-in.** When the user starts speaking, TTS stops within about 300 ms, the in-flight agent turn is cancelled, and the new utterance is processed. | P0 |
| V6 | STT/TTS language follows session language. Hinglish input is understood. The TTS voice matches the reply language. | P0 |
| V7 | A short filler line ("ek second, check kar raha hoon…") plays if a tool call takes longer than about 1 s. | P1 |
| V8 | A text input fallback uses the same agent session, for noisy demos. | P1 |

**Shopping agent**

| ID | Requirement | Pri |
|---|---|---|
| A1 | Search products by description, brand, category and price filters ("under 500 rupees"), including Hinglish and Hindi terms. | P0 |
| A2 | Product details, stock, and reviews summary. | P0 |
| A3 | Cart: view, add, change quantity, remove, clear, and total. Resolves references like "that one", "the second one" and "the cheaper one". | P0 |
| A4 | Checkout with the saved or spoken address. Order history, status and cancellation. | P0 |
| A5 | Recipe → shopping list → confirm → bulk add to cart (existing flow, kept). | P0 |
| A6 | **Confirmation gate.** Checkout, clear cart, cancel order, delete review, and bulk adds over ₹2,000 need an explicit spoken "yes". The bot reads back what it's about to do first. | P0 |
| A7 | Ambiguity handling: if a search returns several close matches, the bot asks one short question rather than guessing. | P0 |
| A8 | Write reviews by voice (rating plus comment). | P1 |
| A9 | "Reorder my usual" / "same as last time", using order history and memory. | P1 |

**Memory & sessions**

| ID | Requirement | Pri |
|---|---|---|
| M1 | **Session = one voice connection.** Each session has its own conversation thread (`thread_id = session_id`). | P0 |
| M2 | Short-term memory survives service restarts (Postgres checkpointer). | P0 |
| M3 | Reconnecting within 30 minutes resumes the previous session rather than starting fresh. | P0 |
| M4 | Long context is trimmed to the last N messages plus a rolling summary, so latency doesn't grow over a long session. | P0 |
| M5 | **Long-term user memory:** preferences such as diet, preferred brands, usual quantities, preferred language and default address. These are extracted at session end and injected at session start. | P0 |
| M6 | The user can say "forget that I'm vegetarian" or "what do you know about me?" | P1 |
| M7 | Session list and transcript view in the frontend. | P2 |

**Frontend**

| ID | Requirement | Pri |
|---|---|---|
| F1 | Voice console with a connect/disconnect button, mic level, a live user transcript (interim and final), the bot transcript, and a speaking indicator. | P0 |
| F2 | JWT from login is passed to the voice session. Voice is disabled when logged out. | P0 |
| F3 | Live cart panel that updates as soon as the agent changes the cart (server event, no polling). | P0 |
| F4 | Tool activity feed ("Searching 'basmati rice'…", "Added to cart ✓"). | P1 |
| F5 | Wire `lib/api.ts` to the real REST API for the products, cart and orders pages. | P1 |

### 4.2 Non-functional

| ID | Requirement | Target |
|---|---|---|
| N1 | **Latency:** end of user speech → first bot audio | p50 ≤ 1.5 s, p95 ≤ 2.5 s, for turns with one tool call |
| N2 | Barge-in reaction: user starts speaking → bot audio stops | ≤ 300 ms |
| N3 | LLM calls per simple turn | ≤ 2 (router + specialist). Today it's 3+. |
| N4 | Reliability: tool or LLM errors become one spoken sentence, never a stack trace or silence. Retries on network errors; 8 s timeout per tool. | — |
| N5 | Security: the JWT is validated at the gateway and passed downstream, never logged, and never visible to the LLM. Admin and auth MCP tools are never exposed to the agent. | — |
| N6 | Observability: each turn logs `session_id`, `turn_id` and per-stage timings (VAD end, STT final, router, first token, first audio, tools). | — |
| N7 | Evaluation: a scripted eval of at least 15 text conversations (EN, HI, Hinglish) checking tool choice and final cart state, plus a latency report from real voice runs. | — |
| N8 | Runs locally with one command (`docker compose up` or a `make dev` script). Works on Windows dev. | P1 |

### 4.3 Out of scope (this submission)

Payments, phone/PSTN calls, admin UI, a vector database (pgvector is P2), speaker identification, mobile app.

## 5. Architecture

### 5.1 System overview

```
                    WebRTC (audio both ways) + RTVI data channel (events)
┌────────────────┐ ◄──────────────────────────────────────────────► ┌──────────────────────────────────────────────┐
│ Frontend       │                                                   │ Voice Gateway  (new: voice_gateway/, :8010)  │
│ React + Vite   │  POST /api/offer  (SDP + JWT)                     │ FastAPI + Pipecat                            │
│ Pipecat client │ ────────────────────────────────────────────────► │                                              │
│ JS SDK         │                                                   │ transport.in → VAD → Gnani STT (WS)          │
└───────┬────────┘                                                   │   → AgentBridge → Gnani TTS (WS) → transport │
        │ REST (pages)                                               └──────────────────┬───────────────────────────┘
        │                                                                               │ HTTP + SSE (token stream)
        │                                                                               ▼
        │                                                            ┌──────────────────────────────────────────────┐
        │                                                            │ Agent Service  (agent/, :8002)               │
        │                                                            │ FastAPI + LangGraph                          │
        │                                                            │ router → specialists → (confirm gate)        │
        │                                                            │ Postgres checkpointer + memory store         │
        │                                                            └───────┬──────────────────────┬───────────────┘
        │                                                                    │ MCP (streamable HTTP)│ OpenAI-compatible
        │                                                                    ▼  + user JWT          ▼
        │                                                            ┌───────────────────┐   ┌─────────────────────┐
        │                                                            │ MCP Server :8004  │   │ Inference provider  │
        │                                                            └─────────┬─────────┘   │ (deepseek-v4-flash) │
        │                                                                      │ REST + JWT  └─────────────────────┘
        ▼                                                                      ▼
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ Product Service (product_service/, :8000)  FastAPI + SQLAlchemy                            │
└──────────────────────────────────────────────┬────────────────────────────────────────────┘
                                               ▼
                         ┌──────────────────────────────────────────────┐
                         │ PostgreSQL: commerce tables · langgraph       │
                         │ checkpoints · sessions · user memory store    │
                         └──────────────────────────────────────────────┘
```

**What changes:** the Voice Gateway replaces both `manager/` and `STT/`. The agent gains a streaming API, sessions and memory. The MCP server and Product Service stay as they are, with the targeted fixes in §5.6.

### 5.2 Voice Gateway (Pipecat)

**Pipeline**

```
SmallWebRTCTransport.input()
  → SileroVADAnalyzer (stop_secs ≈ 0.5)       # end-of-turn
  → GnaniSTTService  (WebSocket, 16 kHz PCM, interim + final, lang from session)
  → TranscriptForwarder  (RTVI: user transcript to UI)
  → AgentBridge          (custom FrameProcessor, below)
  → GnaniTTSService  (WebSocket, voice per language, supports interruption)
  → SmallWebRTCTransport.output()
PipelineParams(allow_interruptions=True, enable_metrics=True)
```

- **Transport:** `SmallWebRTCTransport` (peer-to-peer WebRTC, no third-party account). The browser handles echo cancellation, which matters for barge-in because otherwise the bot hears itself. *Fallback:* `FastAPIWebsocketTransport` with the protobuf serializer, if WebRTC gives trouble on Windows.
- **Auth:** `POST /api/offer` carries the JWT. The gateway verifies it (shared `SECRET_KEY` with the Product Service), extracts `user_id`, and only then creates the pipeline.
- **AgentBridge** (the core custom piece):
  1. On a final `TranscriptionFrame`, it calls `POST /v1/sessions/{sid}/turns` on the agent with `{text, lang}` and reads the SSE stream.
  2. `token` events become `LLMTextFrame`s. Pipecat's TTS sentence aggregator sends each complete sentence to Gnani TTS, so audio starts after the first sentence.
  3. `tool_start` / `tool_end` / `cart_updated` events become RTVI server messages for the UI. `tool_start` arms the 1 s filler timer (V7).
  4. On `StartInterruptionFrame` (user barged in), it **cancels the HTTP stream task** and tells the agent which part of the reply was actually spoken. Spoken text is tracked from `TTSTextFrame`s.
- **Session lifecycle:** on connect, `POST /v1/sessions` (create or resume, M3). On disconnect, `POST /v1/sessions/{sid}/end`, which triggers summary and memory extraction in the background.

### 5.3 Agent Service (LangGraph)

**Turn graph (latency-first rework of the current supervisor)**

```
START → load_context ─► router ─┬─► product ─┐
        (memory, summary,       ├─► cart     │   default: specialist answers → END
         pending action)        ├─► order    │   (no "supervisor FINISH" round-trip)
                                ├─► review   │
                                ├─► recipe ──┼─► handoff(shopping_list) only when the task needs chaining
                                ├─► shopping_list
                                ├─► confirm_gate  (pending action yes/no/modify)
                                └─► chit-chat reply → END
```

Changes from today:

1. **Specialists end the turn by default.** They hand back only through an explicit `handoff_to_<agent>` tool, for multi-step requests like recipe → list. This cuts one LLM call from almost every turn (N3).
2. **Router fast path.** If there is a pending action or list, a cheap classifier step decides yes/no/modify before any full routing. The router uses structured output with a short prompt.
3. **Streaming:** `graph.astream(..., stream_mode=["messages", "custom"])`. Only tokens from the node producing the final answer are forwarded as `token` events. Tool calls emit `custom` events (`tool_start`, `tool_end`, `cart_updated`).
4. **Built once.** The graph and LLM client are built at startup. The MCP client and its tools are created **per session** (the JWT is fixed per session), not per turn.
5. **Confirmation gate (A6).** Mutating tools in `CONFIRM_REQUIRED = {checkout, clear_cart, update_order(status=Cancelled), delete_review}` are wrapped. Calling one stores a `pending_action` in state and returns "needs confirmation". The specialist reads it back, and the next user turn goes to `confirm_gate`, which runs the action on "yes" (haan / ok / kar do). This generalises the existing `pending_list` pattern.
6. **Cancellation.** If the stream is cancelled mid-turn, the partial AI message is saved with `interrupted=True` and only the spoken text, so the next turn knows what the user actually heard. Tools that already ran stay done, which is why destructive tools sit behind the gate.

**State additions:** `session_id`, `user_id`, `lang`, `summary`, `pending_action`, `user_profile` (loaded memory), alongside the existing `pending_list`, `scratch`, `task` and `hops`.

**Language handling**

- The system prompt carries `lang` and the rule: *reply in the user's language. Hindi goes in Devanagari (for TTS); product names and brands stay in English.*
- **Tool arguments are always in English** ("doodh" → `query="milk"`). This is the cheapest fix for keyword search in Hinglish (A1). The LLM does the translation inside the tool call.
- Prices are spoken as "₹249" → "249 rupees" through a text normaliser before TTS.

### 5.4 Memory & sessions

| Layer | What | Storage | Lifetime |
|---|---|---|---|
| Turn state | Messages, scratch, pending list/action | LangGraph `AsyncPostgresSaver`, `thread_id = session_id` | One session (resumable for 30 min) |
| Rolling summary | Summary of messages trimmed from context | `summary` field in state, updated when history exceeds about 20 messages | One session |
| Session record | `id, user_id, lang, started_at, last_active_at, ended_at, summary` | `sessions` table | Permanent |
| User memory | Preferences: diet, brands, usual quantities, language, address notes | LangGraph `AsyncPostgresStore`, namespace `("users", user_id, "profile")` | Permanent, editable (M6) |

- **Write path:** at session end, one LLM call extracts new or changed facts from the transcript as structured output (`[{key, value, evidence}]`) and upserts them into the store. This runs off the voice path, so it never adds latency.
- **Read path:** `load_context` loads the profile (a few hundred tokens at most) into the system prompt at session start and caches it in state.

### 5.5 Tool calling upgrades

1. **Per-agent tool allow-lists** (kept) plus admin and auth tools hard-blocked.
2. **Compact tool outputs.** MCP tools return voice-relevant fields only (`id, name, brand, price, stock, rating`), capped at 5 results. This cuts tokens and latency.
3. **Timeouts and retries.** 8 s timeout and 1 retry on network or 5xx errors. Errors map to short, speakable messages ("out of stock", "you're not logged in").
4. **Idempotency.** Mutating calls carry a `turn_id`-based idempotency key, so a retried `add_to_cart` doesn't double-add.
5. **Parallel tool calls** where the model supports them (for example, several searches for a shopping list, as `match()` already does with `asyncio.gather`).
6. **Events.** Every tool call emits `tool_start` / `tool_end`. Any successful cart mutation emits `cart_updated` with the new cart, which drives F3.

### 5.6 Product Service & MCP fixes (minimal)

- Rename `Product Service/` → `product_service/`, and drop the `GEMINI_API_KEY` requirement.
- Seed data in **INR** with Indian grocery and electronics items (about 150 products), including Hindi aliases in `specs.aliases` so `ILIKE` also matches "doodh" and "aata" as a backstop.
- Search: add an `aliases` term to the match and score expressions. *(P2: pgvector semantic search.)*

### 5.7 Interfaces

**Gateway (:8010)**

| Endpoint / event | Purpose |
|---|---|
| `POST /api/offer` `{sdp, type, token, lang?}` → SDP answer | Start a WebRTC voice session |
| RTVI `user-transcription` (interim/final), `bot-transcription`, `bot-started/stopped-speaking` | Standard Pipecat client events |
| RTVI server-message `{type: "tool", name, status}` | Tool activity feed (F4) |
| RTVI server-message `{type: "cart_updated", items, total}` | Live cart panel (F3) |
| RTVI server-message `{type: "session", session_id, resumed}` | Session info |

**Agent (:8002)**: all calls carry `Authorization: Bearer <jwt>`.

| Endpoint | Body | Returns |
|---|---|---|
| `POST /v1/sessions` | `{lang}` | `{session_id, resumed}` |
| `POST /v1/sessions/{sid}/turns` | `{text, lang, turn_id}` | **SSE:** `token{text}` · `tool_start{name,args}` · `tool_end{name,ok}` · `cart_updated{...}` · `done{full_text}` · `error{message}` |
| `POST /v1/sessions/{sid}/interrupt` | `{turn_id, spoken_text}` | `204` |
| `POST /v1/sessions/{sid}/end` | — | `202` (memory extraction runs in background) |
| `POST /agent/{user_id}` | `{msg}` | Kept for text and eval compatibility |

### 5.8 Latency budget (N1)

| Stage | Budget |
|---|---|
| VAD end-of-turn silence | 500 ms |
| Gnani STT final after end of speech | ≤ 200 ms (Gnani claims P95 < 200 ms streaming) |
| Router LLM (structured, short prompt) | ≤ 350 ms |
| Specialist LLM to first tool call | ≤ 400 ms |
| Tool round-trip (MCP → Product Service → Postgres) | ≤ 150 ms |
| Specialist first answer token | ≤ 300 ms |
| Gnani TTS first audio byte | ≤ 200 ms |
| **Total to first audio** | **≈ 2.1 s worst case; ≈ 1.4 s for tool-free turns** |

The biggest levers if this budget is missed: (1) a faster or smaller model for the router, (2) skipping the router when a pending action exists, (3) shorter prompts, (4) a lower VAD `stop_secs`.

### 5.9 Target repo layout

```
VoiceCart-2.0/
├── voice_gateway/        # NEW: Pipecat bot (replaces manager/ + STT/)
│   ├── server.py         # FastAPI: /api/offer, JWT check, session create
│   ├── pipeline.py       # transport → VAD → STT → bridge → TTS
│   ├── agent_bridge.py   # SSE client, interruption, RTVI events, filler
│   └── text_norm.py      # ₹ / numbers → speakable text
├── agent/
│   ├── main.py           # /v1/sessions API + legacy /agent
│   ├── graph.py · router.py · agents.py · confirm.py
│   ├── memory.py         # checkpointer, store, summary, extraction
│   ├── tools/            # MCP wrapping (compact, timeouts, confirm, events), recipes
│   └── prompts.py
├── mcp_server/
├── product_service/      # renamed
├── frontend/             # + @pipecat-ai/client-js / client-react, small-webrtc transport
├── eval/                 # scripted conversations + latency report
├── docs/SPEC.md
├── docker-compose.yml    # postgres + services (P1)
└── README.md             # rewritten
```

`manager/` and `STT/` are deleted once the gateway works end to end.

## 6. One-week plan

| Day | Deliverable | Covers |
|---|---|---|
| **1 (Fri–Sat)** | **Spikes.** A minimal Pipecat bot with Gnani STT and TTS over WebSocket and an echo "LLM", tested in Hindi, Hinglish and English. Check whether Hindi TTS reads Devanagari and Latin-script Hinglish well. Fix the gateway → agent auth pass-through. | V1–V3, de-risks D2/D6 |
| 2 | Agent: streaming SSE endpoint, graph built once, MCP client per session, specialists end the turn, router fast path. | A1–A4, N3 |
| 3 | AgentBridge: streaming tokens into TTS, barge-in cancel plus spoken-text tracking, end-to-end voice working. | V4–V6 |
| 4 | Sessions, Postgres checkpointer, resume, summary trimming, long-term memory extraction and injection. | M1–M5 |
| 5 | Tools: confirmation gate, compact outputs, timeouts, idempotency, `cart_updated` events, INR seed data plus aliases, filler line. | A5–A7, V7 |
| 6 | Frontend: Pipecat client, live transcript, cart panel, tool feed, JWT wiring. | F1–F4 |
| 7 | Eval script plus latency report, README rewrite, demo video (EN → Hinglish → barge-in → checkout confirmation → reconnect with memory). | N6, N7 |

**Cut line if time runs short:** drop V7, V8, A8, A9, F4, F5 and N8, in that order. Never cut barge-in, the confirmation gate or memory. Those are the story.

## 7. Risks & open questions

| Risk / question | Mitigation |
|---|---|
| `pipecat-gnani` / `gnani-vachana` version compatibility (plugin tested on Pipecat 1.5.x) | Pin the exact versions from the plugin's README on day 1. |
| Gnani API key quota or rate limits during dev and demo | Confirm limits with Gnani. Cache TTS for fixed phrases (greeting, filler). |
| How Hindi TTS handles Latin-script Hinglish and English product names | Day-1 spike decides the prompt rule (Devanagari vs Latin output). |
| `deepseek-v4-flash` latency and tool-calling quality in Hindi | Measure on day 2. The model is env-swappable, so a faster router model can be used if needed. |
| WebRTC (`aiortc`) on Windows | Fall back to the WebSocket transport. |
| Echo, where the bot hears itself and barges in on its own voice | Browser AEC on WebRTC. Test with laptop speakers, not just headphones. |
| **Open:** does the submission need a hosted demo URL, or are a repo and video enough? | Affects whether deployment is needed this week. |

## 8. Demo script (acceptance test)

1. Log in → open voice → "Hi, mujhe 2 kilo basmati rice aur ek litre Amul doodh chahiye" → bot finds both, states prices in rupees, asks to add.
2. "Haan, add kar do" → cart panel updates live.
3. Ask "what's the cheapest headphone under 2000" → while it's answering, interrupt: "no wait, wireless only" → bot stops instantly and re-searches.
4. "Paneer butter masala banane ke liye kya chahiye?" → recipe → shopping list → "remove the cream" → confirm → bulk add.
5. "Checkout karo" → bot reads back total and address → "yes" → order placed.
6. Disconnect, reconnect → "same order again next week?" / "what do you remember about me?" → shows memory and session resume.
