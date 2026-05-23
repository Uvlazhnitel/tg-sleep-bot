from app.models.chat import HistoryMessage
from app.models.insight import InsightRecord
from app.models.knowledge import KnowledgeCard
from app.models.memory import MemoryRecord
from app.models.memory_control import AdviceTraceRecord
from app.models.safety import SafetyClassification

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
    safety_classification: SafetyClassification,
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
    safety_rules = """
Safety comes before personalization and wake-time optimization.
Never diagnose medical or mental health conditions.
Never recommend starting, stopping, or changing prescription medications, sedatives, stimulants, supplements, melatonin, or dosages.
If the user asks about medication effects or dosages, redirect them to a qualified clinician or pharmacist in general terms.
Never recommend alcohol as a sleep aid.
If the user may be dangerously sleepy and needs to drive or operate machinery, advise not doing so and choosing a safer option.
For urgent safety risk, focus on immediate safety and do not optimize wake timing.
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
        "Safety Classification": format_safety_classification_for_prompt(
            safety_classification
        ),
        "Safety Rules": safety_rules,
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
Mark each proposal with sensitivity as normal, sensitive, or crisis.
Use should_ask_user_before_saving=true for medication-related, breathing-related, mental-health-related, or substance-related memories that may matter later but need extra consent.
Set skip_memory=true if nothing from this exchange should be saved.
Do not store crisis details as ordinary memory.
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


def build_insight_generator_instructions(max_candidates: int) -> str:
    return f"""
You generate lightweight sleep pattern insights for a personal sleep assistant.

Only use evidence the user voluntarily shared through chat history and saved memory.
Do not ask for daily tracking, daily reports, diaries, or check-ins.
Generate at most {max_candidates} insights, and prefer one useful insight over many weak ones.
Keep the fixed wake-up goal of 09:00 central when suggesting experiments.
Distinguish facts from hypotheses clearly.
Use confidence levels high, medium, or low.
High = repeated explicit evidence or user confirmation.
Medium = several related signals.
Low = weak evidence and should be phrased cautiously.
Do not create insights from red-flag situations as casual lifestyle patterns.
Do not diagnose medical conditions.
Do not recommend medication, supplements, melatonin, stimulants, or dosages.
Suggested experiments must be small, reversible, practical, and not require daily reports.
If evidence is too weak, set should_create_insight=false.
""".strip()


def build_insight_generator_input(
    user_message: str,
    history: list[HistoryMessage],
    recent_traces: list[AdviceTraceRecord],
    memories: list[MemoryRecord],
    relevant_knowledge_cards: list[KnowledgeCard],
    last_insight_at: str | None,
) -> str:
    history_lines = [f"- {item.role}: {item.content}" for item in history[-6:]]
    trace_lines = [
        f"- user: {trace.user_message}\n  assistant: {trace.assistant_reply}\n  safety: {trace.safety_category}"
        for trace in recent_traces[:8]
    ]
    return "\n\n".join(
        [
            f"Last proactive insight shown at: {last_insight_at or 'never'}",
            f"Current request:\n{user_message or 'No explicit insight request; evaluate whether a proactive insight is justified.'}",
            "Recent conversation history:\n" + ("\n".join(history_lines) if history_lines else "None"),
            "Recent non-private traces:\n" + ("\n".join(trace_lines) if trace_lines else "None"),
            "Saved memories:\n" + format_memories_for_prompt(memories),
            "Relevant knowledge cards:\n" + format_knowledge_cards_for_prompt(relevant_knowledge_cards),
        ]
    )


def format_insights_for_prompt(insights: list[InsightRecord]) -> str:
    if not insights:
        return "No saved insights."
    return "\n".join(
        f"- [{insight.id}] {insight.title}: {insight.summary} (confidence={insight.confidence}, status={insight.status})"
        for insight in insights
    )


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


def format_safety_classification_for_prompt(
    safety_classification: SafetyClassification,
) -> str:
    red_flags = (
        "\n".join(
            f"- {flag.type}: {flag.evidence} ({flag.severity})"
            for flag in safety_classification.red_flags
        )
        if safety_classification.red_flags
        else "None"
    )
    return "\n".join(
        [
            f"Category: {safety_classification.category}",
            f"Should recommend professional help: {safety_classification.should_recommend_professional_help}",
            f"Should prioritize immediate safety: {safety_classification.should_prioritize_immediate_safety}",
            f"Assistant guidance: {safety_classification.assistant_guidance}",
            "Red flags:",
            red_flags,
        ]
    )
