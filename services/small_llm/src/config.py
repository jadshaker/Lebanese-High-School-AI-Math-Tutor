import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SMALL_LLM_SERVICE_URL = os.getenv("SMALL_LLM_SERVICE_URL", "http://localhost:11434")
    SMALL_LLM_MODEL_NAME = os.environ["SMALL_LLM_MODEL_NAME"]
