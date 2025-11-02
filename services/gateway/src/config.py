import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        LARGE_LLM_URL = os.getenv("LARGE_LLM_SERVICE_URL", "http://large-llm:8001")
