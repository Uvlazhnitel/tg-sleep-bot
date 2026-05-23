from app.models.chat import HistoryMessage
from app.models.memory import MemoryRecord
from app.models.safety import SafetyClassification, SafetyRedFlag

SELF_HARM_PATTERNS = (
    "hurt myself",
    "kill myself",
    "want to die",
    "do not want to live",
    "don't want to live",
    "suicide",
    "suicidal",
)

DRIVING_DANGER_PATTERNS = (
    "fell asleep while driving",
    "fall asleep while driving",
    "almost fell asleep while driving",
    "too sleepy to drive",
    "dangerously sleepy",
    "operating machinery",
    "operate machinery",
)

BREATHING_PATTERNS = (
    "stop breathing",
    "stops breathing",
    "breathing pauses",
    "gasping",
    "choking at night",
    "wake up choking",
    "wake up gasping",
    "loud snoring",
)

PERSISTENT_INSOMNIA_PATTERNS = (
    "for 4 weeks",
    "for four weeks",
    "for weeks",
    "multiple weeks",
    "for a month",
)

PANIC_PATTERNS = (
    "panic-like awakenings",
    "wake up in panic",
    "intense fear at night",
    "night panic",
)

SUBSTANCE_PATTERNS = (
    "need alcohol to sleep",
    "use alcohol to fall asleep",
    "rely on alcohol to sleep",
    "need sleeping pills",
    "rely on sleeping pills",
    "depend on sedatives",
    "depend on stimulants",
)

MANIA_PATTERNS = (
    "barely need sleep",
    "don't need sleep",
    "do not need sleep",
    "high energy without sleep",
    "manic",
    "mania",
)

UNUSUAL_SLEEP_BEHAVIOR_PATTERNS = (
    "sleepwalking",
    "acting out dreams",
    "injured myself during sleep",
    "hurt myself during sleep",
)


class SafetyClassifierService:
    def classify(
        self,
        message: str,
        history: list[HistoryMessage],
        memories: list[MemoryRecord],
    ) -> SafetyClassification:
        lowered = message.lower()
        red_flags: list[SafetyRedFlag] = []

        if self._contains_any(lowered, SELF_HARM_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="self_harm_or_suicide",
                    evidence="User mentioned self-harm, suicide, or not wanting to live.",
                    severity="urgent_safety_risk",
                )
            )

        if self._contains_any(lowered, DRIVING_DANGER_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="dangerous_sleepiness_driving",
                    evidence="User described dangerous sleepiness while driving or operating machinery.",
                    severity="urgent_safety_risk",
                )
            )

        if self._contains_any(lowered, BREATHING_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="possible_sleep_apnea",
                    evidence="User mentioned gasping, choking, loud snoring, or breathing pauses.",
                    severity="medical_red_flag",
                )
            )

        if "insomnia" in lowered and self._contains_any(lowered, PERSISTENT_INSOMNIA_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="persistent_insomnia",
                    evidence="User described insomnia or serious sleep difficulty lasting weeks.",
                    severity="medical_red_flag",
                )
            )

        if (
            "severe daytime sleepiness" in lowered
            or "cannot function" in lowered
            or "can't function" in lowered
        ):
            red_flags.append(
                SafetyRedFlag(
                    type="severe_daytime_sleepiness",
                    evidence="User described severe daytime sleepiness or impaired daytime functioning.",
                    severity="medical_red_flag",
                )
            )

        if self._contains_any(lowered, PANIC_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="panic_like_awakenings",
                    evidence="User described repeated nighttime panic-like symptoms.",
                    severity="medical_red_flag",
                )
            )

        if self._contains_any(lowered, SUBSTANCE_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="substance_sleep_dependence",
                    evidence="User described relying on alcohol, sedatives, sleeping pills, or stimulants to sleep or wake.",
                    severity="medical_red_flag",
                )
            )

        if self._contains_any(lowered, MANIA_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="possible_mania_like_sleep_loss",
                    evidence="User described a markedly reduced need for sleep with high energy.",
                    severity="medical_red_flag",
                )
            )

        if self._contains_any(lowered, UNUSUAL_SLEEP_BEHAVIOR_PATTERNS):
            red_flags.append(
                SafetyRedFlag(
                    type="dangerous_sleep_behavior",
                    evidence="User described potentially dangerous unusual sleep behaviors.",
                    severity="medical_red_flag",
                )
            )

        if (
            ("medication" in lowered or "medicine" in lowered or "dose" in lowered or "dosage" in lowered)
            and ("sleep" in lowered or "insomnia" in lowered or "awake" in lowered)
        ):
            red_flags.append(
                SafetyRedFlag(
                    type="medication_sleep_concern",
                    evidence="User connected sleep issues or dosage questions to medication or supplements.",
                    severity="medical_red_flag",
                )
            )

        if any(flag.severity == "urgent_safety_risk" for flag in red_flags):
            return SafetyClassification(
                category="D",
                red_flags=red_flags,
                should_recommend_professional_help=True,
                should_prioritize_immediate_safety=True,
                assistant_guidance=(
                    "Prioritize immediate safety. Do not focus on wake-time optimization. "
                    "Encourage emergency services, crisis support, nearby human support, or avoiding dangerous activities like driving."
                ),
            )

        if red_flags:
            return SafetyClassification(
                category="C",
                red_flags=red_flags,
                should_recommend_professional_help=True,
                should_prioritize_immediate_safety=False,
                assistant_guidance=(
                    "Recommend discussing this with a qualified healthcare professional. "
                    "Do not diagnose. Provide only safe, general sleep advice."
                ),
            )

        if self._is_mild_concern(lowered):
            return SafetyClassification(
                category="B",
                red_flags=[],
                should_recommend_professional_help=False,
                should_prioritize_immediate_safety=False,
                assistant_guidance=(
                    "Give practical advice and mention that if the issue continues or worsens, professional guidance may help."
                ),
            )

        return SafetyClassification(
            category="A",
            red_flags=[],
            should_recommend_professional_help=False,
            should_prioritize_immediate_safety=False,
            assistant_guidance=(
                "Give normal practical sleep advice and keep the 09:00 wake-up goal central."
            ),
        )

    @staticmethod
    def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in text for pattern in patterns)

    @staticmethod
    def _is_mild_concern(text: str) -> bool:
        return any(
            phrase in text
            for phrase in (
                "for a few days",
                "for a couple of days",
                "sleeping badly for a few days",
                "tired today after a late night",
                "few bad nights",
            )
        )
