# tg-sleep-bot

Personal sleep assistant chatbot focused on helping a single user wake up every day at 09:00.

## Current status

This repository now includes a Phase 5 backend prototype:

- Python 3.13 + FastAPI HTTP service
- `POST /chat` endpoint backed by the OpenAI Responses API
- persistent typed memory stored in SQLite
- curated local knowledge cards for practical sleep guidance
- lightweight personalization that adapts to what helped or did not help
- deterministic safety layer for red flags, medical boundaries, and crisis routing
- fixed user goal plus editable preferences and patterns
- no Telegram adapter yet

The assistant is designed to be:

- a free-form sleep advice chatbot
- practical, concise, and non-judgmental
- science-based and explicitly non-medical
- transparent and editable in how it uses memory
- grounded by a small curated sleep knowledge base
- personalized without requiring daily reports
- safety-first when red flags are present
- ready for later deeper analytics or integrations

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

Give direct feedback on a memory:

```bash
curl -X POST http://127.0.0.1:8000/memory/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "memory_id":"<memory_id>",
    "feedback":"confirmed"
  }'
```

## How memory works

The bot stores only durable, useful information such as:

- fixed goals
- preferences
- recurring patterns
- worked-before strategies
- did-not-work strategies
- cautious hypotheses

Phase 4 adds simple support strength signals to memories:

- `confidence`
- `evidence_count`
- `positive_count`
- `negative_count`
- `last_confirmed_at`

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
- say `That helped yesterday.`
- say `That didn't work for me.`
- say `Actually, that's wrong.`
- say `Remember that I usually need a slow morning.`

Phase 5 adds a safety-aware memory filter:

- crisis details are not stored as ordinary long-term memory
- diagnosis-like memories are rejected
- sensitive medical specifics are blocked unless rewritten into a neutral guardrail-style memory
- Category D urgent-risk chats skip normal memory extraction entirely

## How personalization works

Phase 4 does not track every day or require reports. Instead, it personalizes advice by combining:

1. the current situation
2. the user's 09:00 wake-up goal
3. relevant durable memories
4. what worked before
5. what did not work
6. cautious hypotheses
7. curated knowledge cards

Confidence levels are simple and deterministic:

- high confidence: explicit user statements or repeated confirmed memories
- medium confidence: partially confirmed patterns or repeated helpful interventions
- low confidence: tentative hypotheses that should not be treated as facts

Examples of feedback the bot can use:

- `That helped yesterday.`
- `That didn't work for me.`
- `Actually, coffee doesn't affect my sleep.`
- `Remember that I usually need a slow morning.`

The assistant uses a compact personalization context instead of dumping all memories into the prompt.

## Safety layer

Phase 5 adds a deterministic backend safety classifier before reply generation. It looks at the current message, recent context, and relevant memories, then assigns one of four categories:

- `A`: normal sleep routine issue
- `B`: mild concern that may need monitoring if it continues
- `C`: medical red flag worth discussing with a qualified healthcare professional
- `D`: urgent safety risk that should trigger immediate support guidance

Examples of red flags the classifier looks for:

- sleep difficulty lasting multiple weeks
- severe daytime sleepiness that affects driving, work, or daily functioning
- loud snoring, gasping, choking, or possible breathing pauses
- panic-like awakenings
- major mood changes, hopelessness, or severe anxiety
- thoughts of self-harm or suicide
- relying on alcohol, sedatives, stimulants, or sleeping pills to sleep or wake
- medication-related sleep problems
- unusual dangerous sleep behaviors

Safety rules for the assistant:

- it can give general sleep hygiene and routine advice
- it does not diagnose medical or psychiatric conditions
- it does not recommend prescription medication changes, sedatives, stimulants, supplements, or dosages
- it does not recommend alcohol as a sleep aid
- it recommends professional help for Category C concerns
- it prioritizes immediate safety over the 09:00 wake-up goal for Category D

If the user mentions dangerous sleepiness while driving or operating machinery, the assistant should advise not driving while sleepy and choosing a safer option.

This safety layer is a support tool, not a diagnosis tool or emergency service.

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

Phase 5 also adds safety-oriented cards such as:

- `when_to_seek_professional_help`
- `possible_sleep_apnea_red_flags`
- `severe_daytime_sleepiness`
- `persistent_insomnia`
- `alcohol_or_sedative_dependence`
- `dangerous_sleepiness_driving`
- `self_harm_or_crisis`
- `medication_sleep_concerns`

## Privacy notes

- Memory is stored locally in SQLite at `DATABASE_PATH`
- The bot stores only a narrow set of sleep-related durable memories
- The user can list and archive memories through the API
- The user can edit memories and give explicit memory feedback through the API
- Memory extraction is model-assisted, but the model does not write directly to the database
- Knowledge cards are static curated application content stored locally in the repository
- Sensitive crisis and diagnosis-like details are filtered and not stored as casual long-term memory

## Medical boundary

This bot is an informational sleep assistant, not a doctor. It can help with practical decisions about schedule, naps, caffeine, light, and routine, but it cannot:

- diagnose insomnia, sleep apnea, depression, anxiety disorders, mania, or substance dependence
- prescribe treatment
- recommend medication doses or medication changes
- manage emergencies beyond directing the user to immediate help

## Phase 5 limitations

Phase 5 intentionally does not include:

- Telegram integration
- vector search or embeddings
- dynamic web search
- daily sleep reports or check-ins
- authentication or rate limiting
- perfect memory extraction
- automatic medical diagnosis
- advanced analytics dashboards
- wearable integrations

The safety classifier is not a medical diagnosis tool. It may miss subtle red flags, and it may sometimes be cautious. Crisis and medical resource localization is still generic and should be improved later. Pattern detection is still simple and may be imperfect. Low-confidence memories are treated as hypotheses, and the user can correct or delete memories at any time.

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
- waking up gasping or being told you stop breathing
- almost falling asleep while driving
- asking about medication dosage for sleep
- saying alcohol helps with sleep
- self-harm or crisis language that should prioritize immediate safety

## Documents

- [Phase 0 Product Specification](docs/phase-0-product-spec.md)
