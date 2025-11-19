import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class API_KEYS:
        OPENAI = os.getenv("OPENAI_API_KEY")

    class OLLAMA:
        SERVICE_URL = os.getenv("OLLAMA_SERVICE_URL", "http://localhost:11434")
        MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "deepseek-r1:7b")

    class LLM:
        LARGE_MODEL = "gpt-4o-mini"
        TEMPERATURE = 0.7
        MAX_TOKENS = 1000

    class SERVICES:
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")
        EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8002")
