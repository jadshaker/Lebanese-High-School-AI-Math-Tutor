import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    LARGE_LLM_MODEL_NAME = os.environ["LARGE_LLM_MODEL_NAME"]
    LARGE_LLM_TIMEOUT = float(os.getenv("LARGE_LLM_TIMEOUT", "300"))

    class API_KEYS:
        OPENAI = os.getenv("OPENAI_API_KEY")
