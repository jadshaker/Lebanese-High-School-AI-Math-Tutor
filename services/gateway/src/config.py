import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
        SMALL_LLM_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://small-llm:8005")
        EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8002")
        COMPLEXITY_URL = os.getenv("COMPLEXITY_SERVICE_URL", "http://complexity:8004")
