import re

from app.models.chat import HistoryMessage


class MemoryExtractionPolicy:
    _ACKNOWLEDGEMENTS = {
        "ok",
        "okay",
        "thanks",
        "thank you",
        "got it",
        "understood",
        "понял",
        "поняла",
        "понятно",
        "ок",
        "окей",
        "спасибо",
        "ясно",
    }

    _REPEAT_MARKERS = (
        "usually",
        "often",
        "always",
        "keep ",
        "every time",
        "constantly",
        "regularly",
        "часто",
        "обычно",
        "всегда",
        "постоянно",
        "каждый раз",
        "регулярно",
    )

    _PREFERENCE_MARKERS = (
        "i prefer",
        "i don't want",
        "i do not want",
        "i want",
        "it helps me",
        "works for me",
        "мне помогает",
        "я не хочу",
        "я хочу",
        "мне лучше",
        "мне подходит",
        "для меня лучше",
    )

    _FEEDBACK_MARKERS = (
        "that helped",
        "that didn't work",
        "that did not work",
        "this helped",
        "this didn't work",
        "это помогло",
        "это не помогло",
        "мне помогло",
        "мне не помогло",
    )

    _GOAL_CHANGE_MARKERS = (
        "change my wake-up goal to",
        "change my wake up goal to",
        "i want to wake up at",
        "хочу вставать в",
        "измени мою цель пробуждения на",
    )

    _SENSITIVE_MEMORY_SIGNALS = (
        "melatonin",
        "magnesium",
        "alcohol",
        "caffeine",
        "supplement",
        "medication",
        "medicine",
        "gasping",
        "wake up choking",
        "stop breathing",
        "breathing pauses",
        "мелатонин",
        "магний",
        "алкоголь",
        "кофеин",
        "лекар",
        "задыха",
        "переста",
    )

    _ROUTINE_PATTERNS = (
        r"\bi usually go to bed\b",
        r"\bi usually fall asleep\b",
        r"\bi usually wake up\b",
        r"\bi keep pressing snooze\b",
        r"\bя обычно ложусь\b",
        r"\bя обычно засыпаю\b",
        r"\bя обычно просыпаюсь\b",
        r"\bя постоянно жму snooze\b",
    )

    _TEMPORARY_TIME_PATTERNS = (
        r"\blast night\b",
        r"\byesterday\b",
        r"\btonight\b",
        r"\btoday\b",
        r"\bthis morning\b",
        r"\bсегодня\b",
        r"\bвчера\b",
        r"\bсегодня ночью\b",
        r"\bэтой ночью\b",
        r"\bсегодня утром\b",
    )

    def should_run_extraction(
        self,
        message: str,
        history: list[HistoryMessage],
        safety_category: str,
    ) -> bool:
        del history
        if safety_category == "D":
            return False

        lowered = message.strip().lower()
        if not lowered:
            return False
        if lowered in self._ACKNOWLEDGEMENTS:
            return False
        if len(lowered.split()) <= 3 and not self._has_strong_signal(lowered):
            return False
        if self._is_pure_one_off_update(lowered):
            return False
        return self._has_strong_signal(lowered)

    def _has_strong_signal(self, lowered: str) -> bool:
        return (
            any(marker in lowered for marker in self._REPEAT_MARKERS)
            or any(marker in lowered for marker in self._PREFERENCE_MARKERS)
            or any(marker in lowered for marker in self._FEEDBACK_MARKERS)
            or any(marker in lowered for marker in self._GOAL_CHANGE_MARKERS)
            or any(marker in lowered for marker in self._SENSITIVE_MEMORY_SIGNALS)
            or any(re.search(pattern, lowered) for pattern in self._ROUTINE_PATTERNS)
        )

    def _is_pure_one_off_update(self, lowered: str) -> bool:
        has_temporary_time = any(
            re.search(pattern, lowered) for pattern in self._TEMPORARY_TIME_PATTERNS
        )
        return has_temporary_time and not self._has_strong_signal(lowered)
