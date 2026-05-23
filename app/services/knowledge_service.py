import json
import re
from pathlib import Path

from pydantic import TypeAdapter

from app.models.knowledge import KnowledgeCard
from app.models.memory import MemoryRecord

RED_FLAG_TERMS = {
    "persistent insomnia",
    "weeks",
    "severe daytime sleepiness",
    "falling asleep while driving",
    "loud snoring",
    "breathing pauses",
    "panic-like awakenings",
    "major mood changes",
    "sedatives",
    "stimulants",
    "daily functioning",
}

FALLBACK_TOPICS = (
    "stable_wake_time",
    "sleep_pressure",
    "wind_down_routine",
    "adult_sleep_duration",
)

SAFETY_TOPIC_MAP = {
    "possible_sleep_apnea": "possible_sleep_apnea_red_flags",
    "severe_daytime_sleepiness": "severe_daytime_sleepiness",
    "persistent_insomnia": "persistent_insomnia",
    "substance_sleep_dependence": "alcohol_or_sedative_dependence",
    "dangerous_sleepiness_driving": "dangerous_sleepiness_driving",
    "self_harm_or_suicide": "self_harm_or_crisis",
    "medication_sleep_concern": "medication_sleep_concerns",
}


def tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", value.lower()))


class KnowledgeService:
    def __init__(self, knowledge_cards_path: str) -> None:
        self.knowledge_cards_path = Path(knowledge_cards_path)
        self._cards = self._load_cards()

    def list_knowledge_cards(self) -> list[KnowledgeCard]:
        return [card for card in self._cards if card.active]

    def get_knowledge_card_by_topic(self, topic: str) -> KnowledgeCard | None:
        for card in self.list_knowledge_cards():
            if card.topic == topic:
                return card
        return None

    def get_relevant_knowledge_cards(
        self,
        message: str,
        memories: list[MemoryRecord],
        safety_red_flag_types: list[str] | None = None,
    ) -> list[KnowledgeCard]:
        active_cards = self.list_knowledge_cards()
        message_tokens = tokenize(message)
        memory_tokens: set[str] = set()
        for memory in memories:
            memory_tokens.update(tokenize(memory.content))

        scored: list[tuple[float, KnowledgeCard]] = []
        for card in active_cards:
            score = self._score_card(card, message_tokens, memory_tokens)
            if score > 0:
                scored.append((score, card))

        scored.sort(key=lambda item: (-item[0], item[1].topic))
        selected: list[KnowledgeCard] = [card for _, card in scored[:6]]

        if self._has_red_flag(message):
            red_flag_card = self.get_knowledge_card_by_topic(
                "when_to_seek_professional_help"
            )
            if red_flag_card and all(card.id != red_flag_card.id for card in selected):
                selected.insert(0, red_flag_card)
                selected = selected[:6]

        for red_flag_type in safety_red_flag_types or []:
            topic = SAFETY_TOPIC_MAP.get(red_flag_type)
            if topic is None:
                continue
            card = self.get_knowledge_card_by_topic(topic)
            if card and all(existing.id != card.id for existing in selected):
                selected.insert(0, card)
                selected = selected[:6]

        if len(selected) < 3:
            for topic in FALLBACK_TOPICS:
                fallback = self.get_knowledge_card_by_topic(topic)
                if fallback and all(card.id != fallback.id for card in selected):
                    selected.append(fallback)
                if len(selected) >= 3:
                    break

        return selected[:6]

    def _load_cards(self) -> list[KnowledgeCard]:
        adapter = TypeAdapter(list[KnowledgeCard])
        data = json.loads(self.knowledge_cards_path.read_text(encoding="utf-8"))
        return adapter.validate_python(data)

    def _score_card(
        self,
        card: KnowledgeCard,
        message_tokens: set[str],
        memory_tokens: set[str],
    ) -> float:
        tag_tokens = set(card.tags)
        topic_tokens = tokenize(card.topic.replace("_", " "))
        text_tokens = tokenize(
            " ".join(
                [
                    card.title,
                    card.claim,
                    card.practical_rule,
                    card.when_to_use,
                    card.avoid_advising,
                ]
            )
        )

        score = 0.0
        score += 3.0 * len(message_tokens & tag_tokens)
        score += 2.5 * len(message_tokens & topic_tokens)
        score += 1.0 * len(message_tokens & text_tokens)
        score += 0.5 * len(memory_tokens & tag_tokens)
        score += 0.25 * len(memory_tokens & text_tokens)

        if card.topic == "stable_wake_time" and (
            "wake" in message_tokens or "alarm" in message_tokens or "morning" in message_tokens
        ):
            score += 1.0

        return score

    @staticmethod
    def _has_red_flag(message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in RED_FLAG_TERMS)
