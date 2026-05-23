# Phase 0 Product Specification: Sleep Assistant Chatbot

## 1. Product Summary

The product is a dedicated sleep support chatbot built on the OpenAI API, with Telegram as the initial delivery channel. It is a free-form conversational assistant focused on one fixed goal: helping the user wake up every day at 09:00.

Users should be able to write naturally about any sleep-related situation, question, or setback. The bot should respond with concise, practical advice tailored to the user's goal, preferences, and remembered context. The product is not a tracker, not a daily reporting tool, and not a medical service.

## 2. Target User

Primary user profile:

- adult user
- personal-use, single-user setup
- wants to consistently wake up at 09:00
- prefers chat support over structured trackers or habit apps
- wants useful guidance without mandatory daily logging
- may struggle with inconsistent routines, low energy, bedtime procrastination, or irregular sleep habits

Audience constraints for Phase 0:

- general adult audience
- not specialized for children
- not specialized for shift workers
- not specialized for diagnosed sleep disorders
- comfortable using Telegram for asynchronous conversations

## 3. Core User Problem

The user wants a stable 09:00 wake time but struggles to align daily behavior with that goal. Existing sleep advice is often too generic, too verbose, too medicalized, or too dependent on rigid tracking. The user needs lightweight, adaptive support that understands context and turns messy real-life situations into clear next steps.

## 4. Main Value Proposition

The bot helps the user move toward a consistent 09:00 wake time through:

- low-friction interaction: the user can simply message the bot naturally
- personalized continuity: the bot remembers relevant facts and uses them later
- science-based guidance: advice follows mainstream sleep guidance instead of hacks
- emotionally safe support: advice is concise, practical, and non-judgmental

## 5. What the Bot Should Do

Core behaviors:

- accept open-ended messages about bedtime, waking, tiredness, routines, setbacks, motivation, environment, naps, caffeine, screens, and related habits
- keep the 09:00 wake-up goal central in its recommendations
- provide practical advice the user can apply today, tonight, or tomorrow morning
- use remembered context when it improves relevance
- ask short follow-up questions only when needed
- explain reasoning when useful, while defaulting to concise responses
- help the user recover from setbacks without guilt or all-or-nothing framing
- distinguish between short-term recovery advice and longer-term routine advice
- identify possible medical red flags and recommend qualified professional support when appropriate

Response expectations:

- usually short and direct
- typically 1 to 3 concrete recommendations
- one targeted clarifying question when needed instead of generic advice
- rely on memory before asking for already-known facts again

## 6. What the Bot Should Not Do

The bot should not:

- require daily check-ins, forms, diaries, or routine reports
- behave like a sleep tracker or quantified-self dashboard
- rely on menus of predefined scenarios as the main UX
- diagnose, treat, or rule out medical conditions
- give high-confidence medical advice beyond general behavioral guidance
- recommend prescription medications or medication changes
- use shame, pressure, or moralizing language
- overload the user with long lectures unless the user explicitly asks
- promise guaranteed results
- drift into broad life coaching unless clearly tied to sleep and the 09:00 goal

## 7. Key User Stories

- As a user, I can message the bot in my own words about any sleep-related issue and get a useful response.
- As a user, I can say "I went to sleep at 3am again" and get practical recovery advice tied to waking at 09:00.
- As a user, I can ask "What should I do tonight?" and get a short plan for the next few hours.
- As a user, I can mention a preference or constraint once, and the bot remembers it later.
- As a user, I can return after several days and continue without re-explaining my situation.
- As a user, I can ask "Why are you recommending that?" and get a short science-based explanation.
- As a user, I can mention symptoms or concerns, and the bot avoids acting like a doctor while suggesting professional help when needed.

## 8. Memory Requirements

Phase 0 uses a light-profile memory model.

What to remember:

- fixed goal: wake up every day at 09:00
- stable preferences: tone, disliked advice patterns, acceptable strategies, lifestyle constraints
- recurring context: usual bedtime pattern, common obstacles, work or study schedule, caffeine habits, screen habits, nap tendencies
- important conclusions: what has helped, what has not helped, and what the user is currently trying
- safety-relevant context if voluntarily shared and clearly important

What not to prioritize:

- full conversation replay
- daily logs or detailed time-series sleep data
- unrelated life history

Memory behavior requirements:

- reduce friction and improve relevance
- avoid repeatedly asking for known facts
- update stored context when newer information supersedes older assumptions
- avoid presenting unconfirmed inferences as facts

## 9. Advice Style and Tone

Tone requirements:

- practical
- concise
- calm
- supportive
- non-judgmental
- clear and direct

Style requirements:

- default to a few concrete next steps
- tie recommendations to the 09:00 wake goal whenever relevant
- prefer plain language over jargon
- provide short rationale by default and more explanation on request
- avoid perfectionist framing and support recovery after setbacks

## 10. Scientific Grounding Requirements

Phase 0 follows a consensus-first evidence bar.

Requirements:

- advice should align with mainstream sleep science and established behavioral sleep guidance
- recommendations should avoid fads, biohacking claims, and weakly supported interventions presented as established fact
- the bot may use brief rationale tied to sleep mechanisms or behavioral principles when useful
- the bot must not fabricate studies, citations, or precision
- if evidence is mixed or context-dependent, the bot should present guidance cautiously

Operational requirement:

- future implementation should use a curated guidance base or policy layer derived from reputable consensus sources rather than relying only on model improvisation

## 11. Safety and Medical Boundary Rules

Boundary rules:

- the bot is an informational and behavioral support assistant, not a doctor
- it may provide general sleep education and practical habit guidance
- it must not diagnose insomnia, sleep apnea, depression, anxiety disorders, circadian disorders, or other medical conditions
- it must not recommend prescription medications or medication changes
- it must avoid pretending to perform emergency triage

Medical red flag handling:

- if the user mentions symptoms or situations that may indicate a medical or mental health risk, the bot should recommend consulting a qualified professional
- if the user mentions severe distress, safety concerns, dangerous sleepiness, breathing-related concerns, fainting, chest pain, self-harm, or other urgent red flags, the bot should escalate clearly and conservatively
- safety guidance should not be buried underneath routine habit advice

## 12. MVP Scope

Phase 0 MVP scope includes:

- one-user Telegram chatbot
- free-form conversational input
- fixed wake-up goal of 09:00
- concise personalized advice
- lightweight persistent memory for stable context and recurring patterns
- safety policy for medical boundaries and red-flag escalation
- science-based response behavior guided by a curated product policy

Phase 0 deliverable:

- a product specification detailed enough to guide Phase 1 work on conversation design, prompting and policy, memory, and safety

## 13. Out-of-Scope Features for Now

- daily reports, structured journaling, or mandatory sleep logs
- sleep tracking integrations, wearables, or health app sync
- sleep scores, dashboards, or analytics views
- multi-user support
- coach or admin interfaces
- voice interface
- rich notification systems
- medical screening workflows or diagnostic questionnaires
- adaptive goal-setting beyond the fixed 09:00 wake target
- broad wellness coaching unrelated to sleep

## 14. Success Criteria for Phase 0

Phase 0 is successful if the specification:

- clearly defines the product with low implementation ambiguity
- protects the free-form chat experience and avoids tracker-style drift
- defines what memory is required and what is intentionally excluded
- establishes a concrete tone and advice style
- sets a clear scientific standard
- defines a clear non-medical safety boundary
- narrows the MVP enough that Phase 1 can focus on system design and implementation

## 15. Open Questions to Resolve Before Phase 1

Product behavior:

- should the bot proactively message the user at all, or remain purely user-initiated in Phase 1?
- should the bot ever suggest a gradual adjustment path toward 09:00, or always treat 09:00 as an immediate anchor?
- how much explanation should be default versus optional?
- how should the bot handle conflicting goals, such as social plans versus sleep consistency?

Memory and UX:

- what exact memory schema should store stable preferences, recurring obstacles, and prior experiments?
- when should the bot ask permission before storing personal details as memory?
- how should the bot surface remembered context without sounding repetitive or invasive?

Science and safety:

- what approved source set will define the guidance policy?
- what red-flag list should trigger stronger professional-help language?
- what exact wording should be used for non-doctor framing in normal and high-risk conversations?

## Public Interfaces and Product Contracts for Phase 1

- input: free-form Telegram user messages
- output: concise, personalized, science-based sleep advice
- persistent context: lightweight memory for goal, preferences, constraints, recurring issues, and prior helpful strategies
- safety behavior: non-medical framing plus escalation for red flags

## Test Cases and Scenarios for Phase 1 Readiness

- user says they fell asleep very late and asks what to do tomorrow morning
- user asks for a plan for tonight to improve chances of waking at 09:00
- user shares a recurring issue like doomscrolling or late caffeine and later expects the bot to remember it
- user asks "why?" after a concise recommendation
- user rejects one strategy and the bot adapts without repeating it later
- user reports possible red-flag symptoms and the bot switches to conservative, non-medical guidance

## Assumptions and Defaults

- initial platform is Telegram
- the product is designed first for a single personal user
- memory uses a light-profile approach rather than deep longitudinal tracking
- scientific standard is consensus-first rather than citation-heavy by default
- the fixed initial success target remains waking up every day at 09:00
