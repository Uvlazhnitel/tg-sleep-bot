# tg-sleep-bot

Personal sleep assistant chatbot focused on helping a single user wake up every day at 09:00.

## Current status

This repository now includes a Phase 8 backend prototype:

- Python 3.13 + FastAPI HTTP service
- `POST /chat` endpoint backed by the OpenAI Responses API
- persistent typed memory stored in SQLite
- curated local knowledge cards for practical sleep guidance
- lightweight personalization that adapts to what helped or did not help
- deterministic safety layer for red flags, medical boundaries, and crisis routing
- transparent memory controls, private mode, and advice explanations
- lightweight insights and experiment suggestions from saved memory plus non-private chat traces
- optional settings, reminders, timezone-aware scheduling, and mock integration hooks
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
- explicit about what it remembers and why
- capable of occasional lightweight analytics without becoming a tracker
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
export DEFAULT_TIMEZONE="UTC"
export TELEGRAM_BOT_TOKEN="your_botfather_token_here"
export TELEGRAM_MODE="polling"
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

### 4. Run the Telegram bot in polling mode

Create a bot via BotFather first:

1. Open Telegram and message `@BotFather`
2. Run `/newbot`
3. Choose a bot name and username
4. Copy the token and set `TELEGRAM_BOT_TOKEN`

Then start the bot:

```bash
python -m app.telegram_bot.bot
```

The Telegram bot uses the same internal chat service as the FastAPI `/chat` endpoint. It does not send local HTTP requests back into the API.

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

### Settings

Phase 8 adds a user settings layer with feature flags, timezone handling, quiet hours, and private-mode defaults.

Key endpoints:

- `GET /settings`
- `PATCH /settings`
- `GET /settings/features`
- `POST /settings/features/{feature}/enable`
- `POST /settings/features/{feature}/disable`

Current feature flags:

- `reminders`
- `calendar`
- `health_data`
- `timezone_travel`
- `voice_mode`

### Chat

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I went to sleep at 3:30 and still want to wake up at 9 tomorrow. What should I do?",
    "session_id": "example-session",
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
- ask `What are you using to personalize advice?`
- say `Forget that I often snooze alarms.`
- say `Change my wake-up goal to 08:30.`
- say `That helped yesterday.`
- say `That didn't work for me.`
- say `Actually, that's wrong.`
- say `Remember that I usually need a slow morning.`
- say `Why did you recommend that?`
- say `Don't remember this.`
- say `Private mode.`

Phase 5 adds a safety-aware memory filter:

- crisis details are not stored as ordinary long-term memory
- diagnosis-like memories are rejected
- sensitive medical specifics are blocked unless rewritten into a neutral guardrail-style memory
- Category D urgent-risk chats skip normal memory extraction entirely

Phase 6 adds trust and transparency controls:

- memory summaries are grouped into readable categories
- the user can delete or correct remembered items in natural language
- memory can be turned off for a session with `session_id`
- the assistant can explain recent advice in plain language
- sensitive memory proposals pause and ask before saving

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

## Memory transparency

Natural-language memory UX now supports:

- `What do you remember about me?`
- `Show my memory.`
- `Forget that I snooze a lot.`
- `Coffee doesn't affect my sleep.`
- `Change my wake-up goal to 08:30.`
- `Why did you recommend that?`
- `Don't remember this.`
- `Private mode.`

The readable memory summary is grouped into:

- Goal
- Preferences
- Patterns
- Hypotheses
- What worked before
- What did not work
- Safety-relevant notes

Normal chat responses never expose raw memory JSON, internal prompts, or internal memory ids.

## Private mode and memory control

Phase 6 adds session-scoped memory control. Send a `session_id` with `POST /chat` if you want multi-turn private mode or advice explanation continuity.

Disable memory for a session:

```bash
curl -X POST http://127.0.0.1:8000/memory/disable \
  -H "Content-Type: application/json" \
  -d '{"session_id":"my-session"}'
```

Re-enable memory for a session:

```bash
curl -X POST http://127.0.0.1:8000/memory/enable \
  -H "Content-Type: application/json" \
  -d '{"session_id":"my-session"}'
```

When memory is off for a session:

- the assistant still answers normally
- new memories are not saved
- pending sensitive-memory confirmations are not created
- private-mode traces are not used later for insight generation

## Advice explanations

Phase 6 stores a lightweight recent advice trace per `user_id + session_id` so the bot can answer questions like:

- `Why did you recommend that?`
- `What are you basing this on?`
- `Is that because of something you remember about me?`

The explanation can mention:

- the `09:00` wake-up goal
- relevant personal memory if it was used
- relevant knowledge-card grounding
- safety context if that changed the advice

It does not expose raw prompts, internal JSON, or classifier output.

## Lightweight insights

Phase 7 adds occasional pattern insights without turning the product into a tracker.

What lightweight analytics means here:

- the bot only uses information the user already volunteered
- it combines saved memory, worked-before and did-not-work signals, hypotheses, and recent non-private advice traces
- it can summarize patterns on request or occasionally surface one proactive insight
- it stays focused on one small experiment instead of logs, charts, or dashboards

Manual insight prompts include:

- `What patterns do you notice?`
- `Do you see any sleep patterns?`
- `What have you learned about my sleep?`
- `Why am I struggling to wake at 9?`
- `What should I experiment with this week?`

Insight confidence levels are intentionally simple:

- high: repeated explicit evidence or direct confirmation
- medium: several related signals
- low: weak evidence and should be treated as a hypothesis

Proactive insight rules:

- never after every message
- at most once per week by default
- skipped during private mode
- skipped when safety concerns should take priority
- skipped when there is not enough meaningful evidence

Natural-language insight controls include:

- `Don't give me proactive insights.`
- `Turn insights back on.`
- `Dismiss this insight.`
- `Forget this insight.`
- `Save this as a pattern.`
- `This insight is wrong.`
- `That experiment helped.`
- `That experiment did not help.`
- `Why do you think that?`
- `What evidence do you have?`
- `How confident are you?`

Experiment feedback updates memory naturally:

- `That experiment helped.` strengthens `worked_before`
- `That experiment did not help.` strengthens `did_not_work`
- saving an insight as a pattern can create or reinforce a durable `pattern` memory

Normal insight explanations stay in plain language and do not expose raw JSON or internal ids.

## Advanced features

Phase 8 keeps advanced features modular and opt-in.

What it adds:

- timezone-aware user settings
- optional reminders with quiet hours
- optional calendar integration through a provider interface
- optional health-data integration through a provider interface
- voice-friendly response mode

What it does not add:

- mandatory integrations
- daily report requirements
- tracker dashboards
- automatic reminder creation without permission
- persistent storage of private calendar event details by default

## Reminders

Reminder endpoints:

- `GET /reminders`
- `POST /reminders`
- `PATCH /reminders/{reminder_id}`
- `DELETE /reminders/{reminder_id}`
- `POST /reminders/send-due`

Supported reminder types:

- `evening_wind_down`
- `morning_wake_support`
- `experiment_followup`
- `custom_sleep_reminder`

Phase 8 reminder delivery is intentionally lightweight:

- reminders are stored in SQLite
- `send-due` performs timezone-aware due scanning
- one-time reminders deactivate after send
- recurring reminders reschedule themselves
- the app does not run an always-on scheduler
- deployments can call `POST /reminders/send-due` from cron or another worker

Natural-language reminder examples:

- `Remind me to start winding down at 23:30.`
- `Remind me tomorrow morning to get light after waking.`
- `What reminders do I have?`
- `Turn off evening reminders.`

## Timezone handling

Phase 8 adds timezone-aware interpretation for reminders and wake-time support.

- the user has a stored profile timezone
- reminders use the effective timezone
- the `09:00` wake goal remains the anchor, but it is interpreted relative to the user timezone
- temporary local-time overrides can be set for a travel week
- travel mentions alone do not silently change persistent settings

## Integrations

Calendar endpoints:

- `POST /integrations/calendar/connect`
- `POST /integrations/calendar/disconnect`
- `DELETE /integrations/calendar/data`

Health endpoints:

- `POST /integrations/health/connect`
- `POST /integrations/health/disconnect`
- `DELETE /integrations/health/data`

Current provider abstractions:

- `CalendarProvider`
- `HealthDataProvider`

Current mock providers:

- `MockCalendarProvider`
- `MockHealthDataProvider`

Phase 8 integration rules:

- integrations are opt-in only
- calendar context is fetched minimally and is not persisted by default
- health sleep summaries can be stored locally so they can be deleted later
- wearable-derived sleep data is treated as approximate, not medical-grade
- neither calendar data nor health data is written into long-term memory

## Privacy and data deletion

For every advanced feature:

- the user can leave it disabled
- the user can disconnect it
- the user can delete stored reminder or imported health data
- the assistant should use the minimum data needed for the current reply
- notifications should avoid sensitive content unless the user explicitly asked for it
- raw provider payloads should not be shown in normal chat replies

## Adding providers

To add a new integration provider later:

- implement the `CalendarProvider` or `HealthDataProvider` interface
- register it in the corresponding service
- keep returned data minimal and summary-oriented
- support disconnect and delete-data flows
- avoid exposing raw provider payloads in normal user responses

## Sensitive memory handling

For normal preferences, goals, and recurring sleep patterns, automatic saving is still allowed.

For sensitive or medical-adjacent proposals such as:

- medication-related sleep concerns
- breathing-related sleep concerns
- substance-reliance concerns
- mental-health-adjacent sleep concerns

the bot asks before saving:

- `Do you want me to remember this for future sleep advice?`

Crisis details are not saved as ordinary memory.

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
- The user can temporarily disable memory by session
- Memory extraction is model-assisted, but the model does not write directly to the database
- Knowledge cards are static curated application content stored locally in the repository
- Sensitive crisis and diagnosis-like details are filtered and not stored as casual long-term memory
- Advice explanations use lightweight trace metadata, not a full transcript archive

## Medical boundary

This bot is an informational sleep assistant, not a doctor. It can help with practical decisions about schedule, naps, caffeine, light, and routine, but it cannot:

- diagnose insomnia, sleep apnea, depression, anxiety disorders, mania, or substance dependence
- prescribe treatment
- recommend medication doses or medication changes
- manage emergencies beyond directing the user to immediate help

## Phase 8 limitations

Phase 8 intentionally still does not include:

- vector search or embeddings
- dynamic web search
- daily sleep reports or check-ins
- authentication or rate limiting
- perfect memory extraction
- automatic medical diagnosis
- advanced analytics dashboards
- real provider OAuth flows by default

Natural-language memory editing is heuristic and may not always identify the right memory on the first try. Ambiguous changes may require clarification. Advice explanations are based on recent stored trace metadata and may be limited for older messages. Insight detection is approximate and only as good as the evidence the user voluntarily shared. Reminder delivery depends on the deployment environment calling the due-scan API. Calendar and health integrations are optional and may be mock providers at first. Wearable data is approximate and not medical-grade. This is not a medical record system. Insights are not medical conclusions. The safety classifier is not a medical diagnosis tool. It may miss subtle red flags, and it may sometimes be cautious. Crisis and medical resource localization is still generic and should be improved later. Pattern detection is still simple and may be imperfect. Low-confidence memories and low-confidence insights are treated as hypotheses, and the user can disable, correct, dismiss, archive, or delete them at any time.

Conversation history is still client-supplied per request and is only used as a short context window.

## Telegram bot

Telegram support is available in polling mode for local development and simple deployments.

- Required env var: `TELEGRAM_BOT_TOKEN`
- Optional env var: `TELEGRAM_MODE=polling`
- Run with: `python -m app.telegram_bot.bot`
- Test with `/start`, `/help`, and normal free-form messages
- Telegram users are mapped to internal users as `telegram:<telegram_user_id>`
- Telegram keeps a small in-memory per-user history window for recent turns

Current limitations:

- polling only
- no webhook deployment flow yet
- no predefined menus
- no daily reports
- no advanced reminder delivery through Telegram yet

Future webhook note:

- a later phase can add `POST /telegram/webhook`
- that mode would require a public HTTPS URL and Telegram `setWebhook`

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
- asking `Why did you recommend that?` after a normal reply
- turning memory off for a session and confirming nothing new is saved
- sensitive memory proposal that should ask for consent before saving
- asking `What patterns do you notice?`
- opting out of proactive insights
- dismissing an insight and confirming it does not keep resurfacing
- saying `That experiment helped.` or `That experiment did not help.`
- enabling and disabling feature flags
- creating a reminder and scanning due reminders
- connecting and disconnecting mock calendar and health providers
- changing timezone and using private mode by default

## Documents

- [Phase 0 Product Specification](docs/phase-0-product-spec.md)
