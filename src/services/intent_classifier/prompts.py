from src.models.schemas import IntentCategory

CLASSIFICATION_PROMPT = """You are an intent classifier for a math tutoring system.
Classify the user's response into ONE of these categories:

- AFFIRMATIVE: User confirms, agrees, or indicates understanding (yes, I know, got it, understood, correct, right)
- NEGATIVE: User denies, disagrees, or indicates lack of understanding (no, I don't know, never learned, unfamiliar, confused)
- PARTIAL: User partially understands or is uncertain (somewhat, a little, not sure, maybe, kind of)
- QUESTION: User asks for clarification or more information (what do you mean, can you explain, how, why)
- SKIP: User wants to skip explanation and get the answer (just tell me, give me the answer, skip)
- OFF_TOPIC: Response is unrelated to the tutoring context

Context: The tutor asked a diagnostic question to gauge the student's understanding.

User response: "{response}"

Reply with ONLY the category name (AFFIRMATIVE, NEGATIVE, PARTIAL, QUESTION, SKIP, or OFF_TOPIC)."""

INTENT_PATTERNS: dict[IntentCategory, list[str]] = {
    IntentCategory.AFFIRMATIVE: [
        r"\byes\b",
        r"\byeah\b",
        r"\byep\b",
        r"\byup\b",
        r"\bsure\b",
        r"\bok\b",
        r"\bokay\b",
        r"\bcorrect\b",
        r"\bright\b",
        r"\bexactly\b",
        r"\bi know\b",
        r"\bi understand\b",
        r"\bi got it\b",
        r"\bunderstood\b",
        r"\bof course\b",
        r"\bdefinitely\b",
        r"\babsolutely\b",
        r"\bfamiliar\b",
        r"\bi remember\b",
        r"\blearned\s+(it|that|this)\b",
    ],
    IntentCategory.NEGATIVE: [
        r"\bno\b",
        r"\bnope\b",
        r"\bnah\b",
        r"\bnot\s+really\b",
        r"\bi\s+don'?t\s+know\b",
        r"\bi\s+don'?t\s+understand\b",
        r"\bnever\s+(learned|heard|seen)\b",
        r"\bunfamiliar\b",
        r"\bconfused\b",
        r"\bi\s+forgot\b",
        r"\bcan'?t\s+remember\b",
        r"\bwhat\s+is\s+that\b",
        r"\bi\s+have\s+no\s+idea\b",
        r"\bnot\s+at\s+all\b",
        r"\bdidn'?t\s+learn\b",
    ],
    IntentCategory.PARTIAL: [
        r"\bmaybe\b",
        r"\bsomewhat\b",
        r"\bkind\s+of\b",
        r"\bsort\s+of\b",
        r"\ba\s+little\b",
        r"\bnot\s+sure\b",
        r"\bi\s+think\s+so\b",
        r"\bprobably\b",
        r"\bpartially\b",
        r"\bsomehow\b",
        r"\bi\s+guess\b",
        r"\bbit\s+rusty\b",
        r"\bvaguely\b",
    ],
    IntentCategory.QUESTION: [
        r"\bwhat\s+(do\s+you\s+mean|is|are|does)\b",
        r"\bhow\s+(do|does|is|can)\b",
        r"\bwhy\b",
        r"\bcan\s+you\s+explain\b",
        r"\bcould\s+you\s+(explain|clarify)\b",
        r"\bwhat'?s\s+that\b",
        r"\bi\s+don'?t\s+get\s+it\b",
        r"\bexplain\s+(that|this|more)\b",
        r"\?\s*$",
    ],
    IntentCategory.SKIP: [
        r"\bjust\s+(tell|give|show)\s+me\b",
        r"\bskip\b",
        r"\bgive\s+me\s+the\s+answer\b",
        r"\btell\s+me\s+the\s+answer\b",
        r"\bi\s+just\s+want\s+the\s+answer\b",
        r"\bget\s+to\s+the\s+point\b",
        r"\bno\s+need\s+to\s+explain\b",
        r"\bjust\s+answer\b",
    ],
}
