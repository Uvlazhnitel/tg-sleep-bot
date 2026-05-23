from app.models.chat import HistoryMessage
from app.models.knowledge import KnowledgeCard
from app.models.memory import MemoryRecord

PHASE_1_PROFILE = """
Wake-up goal: the user wants to wake up every day at 09:00.
Advice preferences: the user wants free-form chat advice, not menus or predefined scenarios.
Reporting preferences: the user does not want daily reports, sleep diaries, or required check-ins.
Advice quality: recommendations should be science-based, practical, concise, and non-judgmental.
Known recurring issues: the user often struggles with snoozing alarms and sometimes wakes earlier than planned at a repeated time.
""".strip()

PHASE_1_BEHAVIOR_RULES = """
You are a personal sleep assistant.
Always take the 09:00 wake-up goal into account.
Give practical advice for the user's current situation.
Prefer short answers with 1 to 3 concrete actions.
Explain the reasoning briefly when useful.
Avoid long lectures unless the user explicitly asks for details.
Ask at most one clarifying question, and only if it is necessary to give a useful answer.
Do not ask the user to fill out daily reports.
Do not force the user into predefined scenarios.
Do not diagnose medical conditions.
If the user describes persistent insomnia, severe daytime sleepiness, breathing pauses, panic-like awakenings, major mood changes, or other medical red flags, recommend professional help clearly and conservatively.
""".strip()

PHASE_1_STYLE_RULES = """
Tone: calm, supportive, concise, and non-judgmental.
Language: plain and practical, without unnecessary jargon.
Framing: help the user recover from setbacks without shame or perfectionism.
""".strip()


def build_phase1_instructions() -> str:
    sections = {
        "Role": "You are the assistant for a personal sleep-support chatbot prototype.",
        "Fixed User Profile": PHASE_1_PROFILE,
        "Assistant Behavior Rules": PHASE_1_BEHAVIOR_RULES,
        "Style Rules": PHASE_1_STYLE_RULES,
        "Safety Boundaries": (
            "You are not a doctor. Do not diagnose conditions, recommend prescription medications, "
            "or claim certainty where general sleep advice is more appropriate."
        ),
    }
    return "\n\n".join(f"{name}:\n{content}" for name, content in sections.items())


def build_assistant_instructions(
    personalization_context: str,
    relevant_knowledge_cards: list[KnowledgeCard],
) -> str:
    knowledge_block = format_knowledge_cards_for_prompt(relevant_knowledge_cards)
    dynamic_rules = """
Use personalization only when relevant to the user's current situation.
Do not mention memory unless it helps the answer.
If a memory is uncertain or low-confidence, phrase it as a possibility rather than a fact.
Do not overfit to weak or stale memories.
Keep the advice practical and tied to the user's wake-up goal.
Prefer strategies that worked before when they are still safe and relevant.
Avoid repeating advice that did not work before unless there is a clear reason.
If memory conflicts with safety or knowledge-card guidance, prioritize safety first, then knowledge, then preference.
If useful, mention previous user context briefly without sounding invasive.
Never ask for daily reports.
""".strip()
    knowledge_rules = """
Use the knowledge cards as grounding for practical sleep advice.
Do not invent scientific claims beyond the cards.
Do not quote or expose source URLs unless the user explicitly asks.
Lead with practical advice, then brief reasoning when useful.
If the cards are not enough to support a strong claim, say you are not fully sure rather than filling in unsupported detail.
Recommend professional help clearly when red-flag situations are relevant.
When useful, naturally cover best action now, why it helps, and what to avoid, but do not force a rigid template every time.
""".strip()
    wake_goal_framing = """
Treat the current fixed_goal memory as the user's active wake-up target.
If no fixed_goal memory is available, default to helping the user wake up at 09:00.
Keep recommendations aligned with protecting or gradually restoring a stable target wake time.
""".strip()

    sections = {
        "Role": "You are the assistant for a personal sleep-support chatbot prototype.",
        "Fixed Assistant Rules": PHASE_1_BEHAVIOR_RULES,
        "Style Rules": PHASE_1_STYLE_RULES,
        "Wake Goal Framing": wake_goal_framing,
        "Personalization Usage Rules": dynamic_rules,
        "Personalization Context": personalization_context,
        "Knowledge Card Usage Rules": knowledge_rules,
        "Relevant Knowledge Cards": knowledge_block,
        "Safety Boundaries": (
            "You are not a doctor. Do not diagnose conditions, recommend prescription medications, "
            "or claim certainty where general sleep advice is more appropriate."
        ),
    }
    return "\n\n".join(f"{name}:\n{content}" for name, content in sections.items())


def build_phase1_input(message: str, history: list[HistoryMessage]) -> list[dict[str, str]]:
    input_items: list[dict[str, str]] = []
    for item in history:
        input_items.append({"role": item.role, "content": item.content})
    input_items.append({"role": "user", "content": message})
    return input_items


def build_memory_extractor_instructions() -> str:
    return """
You extract durable user memory for a personal sleep assistant.

Only propose memories that are durable and useful over time.
Do not save one-off events or temporary context.
Do not infer diagnoses.
Avoid judgmental or shame-based wording.
Save explicit preferences and stable goals.
Save repeated patterns only when the user clearly states them or there is strong evidence.
Save worked_before only when the user says something helped.
Save did_not_work only when the user says something did not help.
Save hypotheses with lower confidence when evidence is weak.
Use update or archive instead of duplicate create when appropriate.
""".strip()


def build_memory_extractor_input(
    user_message: str,
    assistant_reply: str,
    relevant_memories: list[MemoryRecord],
) -> str:
    return "\n\n".join(
        [
            "Current memories:\n" + format_memories_for_prompt(relevant_memories),
            f"Latest user message:\n{user_message}",
            f"Assistant reply:\n{assistant_reply}",
        ]
    )


def format_memories_for_prompt(memories: list[MemoryRecord]) -> str:
    if not memories:
        return "No saved memories yet."

    grouped: dict[str, list[str]] = {}
    for memory in memories:
        grouped.setdefault(memory.type, []).append(
            f"- [{memory.id}] {memory.content} (confidence={memory.confidence:.2f})"
        )

    sections: list[str] = []
    for memory_type in [
        "fixed_goal",
        "preference",
        "pattern",
        "hypothesis",
        "worked_before",
        "did_not_work",
    ]:
        items = grouped.get(memory_type)
        if items:
            sections.append(f"{memory_type}:\n" + "\n".join(items))
    return "\n\n".join(sections)


def format_knowledge_cards_for_prompt(cards: list[KnowledgeCard]) -> str:
    if not cards:
        return "No relevant knowledge cards were retrieved."

    sections: list[str] = []
    for card in cards:
        sections.append(
            "\n".join(
                [
                    f"- [{card.id}] topic={card.topic} title={card.title}",
                    f"  practical_rule: {card.practical_rule}",
                    f"  when_to_use: {card.when_to_use}",
                    f"  avoid_advising: {card.avoid_advising}",
                    f"  evidence_level: {card.evidence_level}",
                    f"  source_name: {card.source_name}",
                ]
            )
        )
    return "\n\n".join(sections)
