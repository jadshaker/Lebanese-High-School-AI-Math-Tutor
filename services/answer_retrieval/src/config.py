import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    CACHE_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))

    class SERVICES:
        EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8002")
        CACHE_URL = os.getenv("CACHE_SERVICE_URL", "http://cache:8003")
        SMALL_LLM_URL = os.getenv(
            "SMALL_LLM_SERVICE_URL", "http://small-llm:8005"
        )
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
