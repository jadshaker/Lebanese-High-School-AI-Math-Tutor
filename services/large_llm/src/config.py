import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    LARGE_LLM_MODEL_NAME = os.environ["LARGE_LLM_MODEL_NAME"]

    class API_KEYS:
        OPENAI = os.getenv("OPENAI_API_KEY")
