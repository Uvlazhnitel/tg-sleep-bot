# tg-sleep-bot

Personal sleep assistant chatbot focused on helping a single user wake up every day at 09:00.

## Current status

This repository now includes a Phase 1 backend prototype:

- Python 3.13 + FastAPI HTTP service
- `POST /chat` endpoint backed by the OpenAI Responses API
- fixed Phase 1 user profile and assistant behavior prompt
- no persistent memory, no database, no Telegram adapter yet

The assistant is designed to be:

- a free-form sleep advice chatbot
- practical, concise, and non-judgmental
- science-based and explicitly non-medical
- ready for later memory and personalization layers

## Project structure

```text
app/
  api/
  core/
  models/
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

## Phase 1 limitations

Phase 1 intentionally does not include:

- persistent long-term memory
- database storage
- Telegram integration
- predefined sleep scenario menus
- daily sleep reports or check-ins
- sleep knowledge cards or retrieval layer
- authentication or rate limiting

Conversation history is client-supplied per request and is only used as a short context window.

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
- red-flag symptoms that should trigger professional-help language

## Documents

- [Phase 0 Product Specification](docs/phase-0-product-spec.md)
