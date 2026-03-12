from src.models.schemas import IntentCategory

CLASSIFICATION_PROMPT = """You are an intent classifier for a math tutoring system.
Classify the user's response into ONE of these categories:

- AFFIRMATIVE: User confirms, agrees, or indicates understanding (yes, I know, got it, understood, correct, right)
- NEGATIVE: User denies, disagrees, or indicates lack of understanding (no, I don't know, never learned, unfamiliar, confused)
- CORRECTION: User corrects or restates their original question/problem (no it is 2x^5, I meant the integral of..., actually the equation is..., sorry I made a mistake)
- PARTIAL: User partially understands or is uncertain (somewhat, a little, not sure, maybe, kind of)
- QUESTION: User asks for clarification or more information (what do you mean, can you explain, how, why)
- SKIP: User wants to skip explanation and get the answer (just tell me, give me the answer, skip)
- ANSWER_ATTEMPT: User attempts to answer the tutor's question or proposes a solution (I think it is 3x, is it x^2?, the answer is 5, it equals 1/x, you subtract the exponents)
- OFF_TOPIC: Response is completely unrelated to math or the tutoring context (my name is Jeff, what's for lunch, I like dogs)

Context: The tutor asked a diagnostic question to gauge the student's understanding.

User response: "{response}"

Reply with ONLY the category name (AFFIRMATIVE, NEGATIVE, CORRECTION, PARTIAL, QUESTION, SKIP, ANSWER_ATTEMPT, or OFF_TOPIC)."""

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
    IntentCategory.CORRECTION: [
        # "no" followed by a correction phrase
        r"\bno\b[,.]?\s*(it\s+is|it's|the\s+question\s+is|i\s+meant|i\s+mean|actually|rather|instead)",
        # "no" followed by mathematical content
        r"\bno\b[,.]?\s+.+([a-z]\s*[\^]|\d+\s*[a-z]|\d+\s*[\^]|\bx\b|\by\b|\bintegral\b|\bderivative\b|\bequation\b|\bfunction\b|\blimit\b|\bsin\b|\bcos\b|\btan\b|\blog\b|\bln\b)",
        # Explicit correction phrases
        r"\bi\s+meant\b",
        r"\bi\s+mean\b",
        r"\bactually\s+(it|the|my)\b",
        r"\blet\s+me\s+correct\b",
        r"\bsorry\b[,.]?\s*(it|the|i|my)\b",
        r"\bwait\b[,.]?\s*(it|the|i|my)\b",
        r"\bmy\s+(question|problem)\s+(is|was)\b",
        r"\bthe\s+(correct|right|actual)\s+(question|problem|equation)\b",
        r"\bi\s+made\s+a\s+mistake\b",
        r"\bthat'?s\s+not\s+(what\s+i|right|correct)\b",
        r"\bwhat\s+i\s+meant\b",
    ],
    IntentCategory.NEGATIVE: [
        # Bare "no" only when it is the entire message
        r"^no[.!]?$",
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
    IntentCategory.ANSWER_ATTEMPT: [
        # "I think it is..." / "I think the answer is..."
        r"\bi\s+think\s+(it\s+is|it's|the\s+answer\s+is|it\s+equals|it\s+would\s+be|we\s+(get|use|need|apply|subtract|add|multiply|divide))\b",
        # "is it..." / "is the answer..."
        r"^\s*is\s+it\b",
        r"\bis\s+the\s+answer\b",
        # "the answer is..." / "it is..." / "it's..." / "it equals..."
        r"\bthe\s+answer\s+is\b",
        r"\bit\s+equals\b",
        r"\bit\s+(is|should\s+be|would\s+be|gives)\s+\d",
        r"\bit\s+(is|should\s+be|would\s+be|gives)\s+[-]?\s*\d*\s*[/\\]?\s*[a-z]",
        # "you subtract/add/multiply/divide..."
        r"\byou\s+(subtract|add|multiply|divide|factor|simplify|integrate|differentiate|apply)\b",
        # "we get..." / "we use..." / "that gives..."
        r"\bwe\s+(get|use|apply|need\s+to)\b",
        r"\bthat\s+gives\b",
        # Mathematical expressions as standalone answers (e.g., "1/x^2", "x^3 + 2", "-2x")
        r"^[\s]*[-]?\s*\d*\s*[/\\]?\s*[a-z]\s*[\^]",
        r"^[\s]*[-]?\s*\d+\s*[/\\]\s*[a-z]",
        # "it's x^2" / "it is 1/x"
        r"\bit'?s\s+[-]?\s*\d*\s*[/\\]?\s*[a-z]",
    ],
}
