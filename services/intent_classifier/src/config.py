import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")

    class CLASSIFIER:
        RULE_CONFIDENCE_THRESHOLD = float(
            os.getenv("INTENT_RULE_CONFIDENCE_THRESHOLD", "0.8")
        )
        USE_LLM_FALLBACK = (
            os.getenv("INTENT_USE_LLM_FALLBACK", "true").lower() == "true"
        )
        LLM_TEMPERATURE = float(os.getenv("INTENT_CLASSIFIER_LLM_TEMPERATURE", "0.1"))
        LLM_MAX_TOKENS = int(os.getenv("INTENT_CLASSIFIER_LLM_MAX_TOKENS", "50"))

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
