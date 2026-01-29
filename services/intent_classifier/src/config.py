import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class OLLAMA:
        SERVICE_URL = os.getenv("OLLAMA_SERVICE_URL", "http://localhost:11434")
        MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "deepseek-r1:7b")

    class CLASSIFIER:
        # Confidence threshold for rule-based classification
        RULE_CONFIDENCE_THRESHOLD = 0.8
        # Use LLM for ambiguous cases
        USE_LLM_FALLBACK = os.getenv("USE_LLM_FALLBACK", "true").lower() == "true"

    # System prompt for LLM-based classification
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
