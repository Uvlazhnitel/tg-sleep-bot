# tg-sleep-bot

Personal sleep assistant chatbot focused on helping a single user wake up every day at 09:00.

## Current status

This repository now includes a Phase 3 backend prototype:

- Python 3.13 + FastAPI HTTP service
- `POST /chat` endpoint backed by the OpenAI Responses API
- persistent typed memory stored in SQLite
- curated local knowledge cards for practical sleep guidance
- fixed user goal plus editable preferences and patterns
- no Telegram adapter yet

The assistant is designed to be:

- a free-form sleep advice chatbot
- practical, concise, and non-judgmental
- science-based and explicitly non-medical
- transparent and editable in how it uses memory
- grounded by a small curated sleep knowledge base
- ready for later deeper personalization layers

## Project structure

```text
app/
  api/
  core/
  models/
  repositories/
  services/
docs/
tests/
```

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set environment variables

At minimum, set `OPENAI_API_KEY`.

```bash
export OPENAI_API_KEY="your_api_key_here"
export OPENAI_MODEL="gpt-4.1-mini"
export OPENAI_EXTRACTOR_MODEL="gpt-4.1-mini"
export DATABASE_PATH="sleep_assistant.db"
export APP_ENV="development"
export ENABLE_DEBUG_METADATA="false"
export KNOWLEDGE_CARDS_PATH="app/data/knowledge_cards.json"
```

You can also copy `.env.example` as a reference:

```bash
cp .env.example .env
```

Note: the app reads real environment variables. The `.env.example` file is documentation, not an auto-loaded config file.

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## API

### Health check

```bash
curl http://127.0.0.1:8000/health
```

Example response:

```json
{
  "status": "ok"
}
```

Optional development-only debug metadata:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I keep snoozing my alarms.",
    "include_debug": true
  }'
```

Debug metadata is only returned when debug mode is enabled by environment configuration.

### Chat

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I went to sleep at 3:30 and still want to wake up at 9 tomorrow. What should I do?",
    "history": [
      { "role": "user", "content": "I often snooze my alarms." },
      { "role": "assistant", "content": "We should keep your 09:00 wake time consistent and make snoozing harder." }
    ]
  }'
```

Example response:

```json
{
  "reply": "Keep your 09:00 wake time tomorrow, avoid trying to compensate by sleeping late, and plan a lighter evening so you can get to bed earlier tomorrow night. If you can, keep naps short or skip them, and get bright light soon after waking. That helps protect your wake time anchor without turning one late night into a longer schedule shift."
}
```

### Memory

List memories:

```bash
curl http://127.0.0.1:8000/memory
```

Archive a memory:

```bash
curl -X DELETE http://127.0.0.1:8000/memory/<memory_id>
```

Update a memory manually:

```bash
curl -X PATCH http://127.0.0.1:8000/memory/<memory_id> \
  -H "Content-Type: application/json" \
  -d '{"content":"User wants to wake up every day at 08:30.","confidence":1.0}'
```

Create a memory manually:

```bash
curl -X POST http://127.0.0.1:8000/memory \
  -H "Content-Type: application/json" \
  -d '{
    "type":"worked_before",
    "content":"Morning light helped the user get out of bed.",
    "confidence":0.9,
    "source":"manual"
  }'
```

## How memory works

Phase 2 stores only durable, useful information such as:

- fixed goals
- preferences
- recurring patterns
- worked-before strategies
- did-not-work strategies
- cautious hypotheses

It does not try to save every message. One-off events like a single late bedtime should usually stay out of long-term memory.

The chat flow is:

1. load relevant saved memories
2. generate the assistant reply
3. run a separate memory extraction step
4. validate the proposed memory updates in backend code
5. save only accepted updates

The user can also manage memory explicitly:

- ask `What do you remember about me?`
- say `Forget that I often snooze alarms.`
- say `Change my wake-up goal to 08:30.`

## What knowledge cards are

Knowledge cards are a small curated local sleep knowledge base. Each card captures one practical sleep principle with:

- a topic and title
- a bounded scientific claim
- a practical rule
- when to use it
- what to avoid advising
- evidence level and source

The bot uses 3 to 6 relevant cards per response when possible. Retrieval is local and heuristic:

- keyword matching against the user message
- tag and topic matching
- light relevance boosting from stored user memories
- forced inclusion of the professional-help card for red-flag messages

Cards guide the advice, but the assistant still answers naturally in chat instead of sounding like an academic article.

### How to add or edit a knowledge card

Knowledge cards live in [app/data/knowledge_cards.json](/Users/uvlazhnitel/Documents/tg-sleep-bot/app/data/knowledge_cards.json).

When editing cards:

- keep claims practical and bounded
- use one reputable source per card
- avoid invented or overly specific causal claims
- avoid diagnosis-style wording
- keep `practical_rule` and `avoid_advising` concrete

Acceptable source families for this phase:

- American Academy of Sleep Medicine / Sleep Education
- CDC
- NHS
- Mayo Clinic
- National Sleep Foundation
- Sleep Foundation

## Privacy notes

- Memory is stored locally in SQLite at `DATABASE_PATH`
- The bot stores only a narrow set of sleep-related durable memories
- The user can list and archive memories through the API
- Memory extraction is model-assisted, but the model does not write directly to the database
- Knowledge cards are static curated application content stored locally in the repository

## Phase 3 limitations

Phase 3 intentionally does not include:

- Telegram integration
- vector search or embeddings
- dynamic web search
- daily sleep reports or check-ins
- authentication or rate limiting
- perfect memory extraction
- automatic medical diagnosis

Scientific advice quality depends on the quality and coverage of the curated cards. The knowledge base is intentionally small for maintainability.

Conversation history is still client-supplied per request and is only used as a short context window.

## Testing

Run the automated tests with:

```bash
pytest
```

Manual smoke scenarios to try:

- late bedtime recovery question
- tonight planning question
- snoozing-alarm question
- repeated early waking question
- caffeine timing question
- concerning symptoms that should surface professional-help guidance
- morning light helped before and becomes `worked_before`
- many alarms did not help and becomes `did_not_work`
- one-off late bedtime gets ignored as memory
- red-flag symptoms that should trigger professional-help language

## Documents

- [Phase 0 Product Specification](docs/phase-0-product-spec.md)
