import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    OLLAMA_SERVICE_URL = os.getenv("OLLAMA_SERVICE_URL", "http://localhost:11434")
    OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "deepseek-r1:7b")
