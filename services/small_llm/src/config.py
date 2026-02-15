import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SMALL_LLM_SERVICE_URL = os.environ["SMALL_LLM_SERVICE_URL"]
    SMALL_LLM_MODEL_NAME = os.environ["SMALL_LLM_MODEL_NAME"]
    SMALL_LLM_API_KEY = os.environ["SMALL_LLM_API_KEY"]
