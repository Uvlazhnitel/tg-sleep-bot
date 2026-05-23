import json

import pytest
from pydantic import ValidationError

from app.models.knowledge import KnowledgeCard
from app.models.memory import MemoryRecord
from app.services.knowledge_service import KnowledgeService


def build_memory(content: str) -> MemoryRecord:
    return MemoryRecord(
        id="m1",
        user_id="default_user",
        type="pattern",
        content=content,
        confidence=0.8,
        source="manual",
        created_at="2026-05-23T00:00:00+00:00",
        updated_at="2026-05-23T00:00:00+00:00",
        last_used_at=None,
        is_archived=False,
    )


def test_knowledge_cards_load_from_json():
    service = KnowledgeService("app/data/knowledge_cards.json")
    cards = service.list_knowledge_cards()

    assert len(cards) >= 15
    assert any(card.topic == "stable_wake_time" for card in cards)


def test_get_relevant_cards_by_keyword_and_tag():
    service = KnowledgeService("app/data/knowledge_cards.json")
    cards = service.get_relevant_knowledge_cards(
        "I keep snoozing my alarms and feel groggy every morning.",
        [build_memory("User often struggles with snoozing alarms.")],
    )

    topics = [card.topic for card in cards]
    assert "snoozing" in topics
    assert "morning_light" in topics


def test_irrelevant_cards_are_not_prioritized_when_avoidable():
    service = KnowledgeService("app/data/knowledge_cards.json")
    cards = service.get_relevant_knowledge_cards(
        "I drink caffeine too late and then I cannot fall asleep.",
        [],
    )

    topics = [card.topic for card in cards[:3]]
    assert "caffeine_timing" in topics
    assert "alcohol_and_sleep" not in topics


def test_red_flag_card_is_retrieved_for_concerning_message():
    service = KnowledgeService("app/data/knowledge_cards.json")
    cards = service.get_relevant_knowledge_cards(
        "I have severe daytime sleepiness and loud snoring with breathing pauses.",
        [],
    )

    assert any(card.topic == "when_to_seek_professional_help" for card in cards)


def test_invalid_knowledge_card_shape_fails_validation(tmp_path):
    path = tmp_path / "bad_cards.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "topic": "",
                    "title": "Bad card",
                    "claim": "Claim",
                    "practical_rule": "Rule",
                    "when_to_use": "Use",
                    "avoid_advising": "Avoid",
                    "evidence_level": "very_strong",
                    "source_name": "Source",
                    "source_url": "https://example.com",
                    "tags": [],
                    "created_at": "2026-05-23T00:00:00+00:00",
                    "updated_at": "2026-05-23T00:00:00+00:00",
                    "active": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        KnowledgeService(str(path))
