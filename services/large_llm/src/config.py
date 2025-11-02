import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class API_KEYS:
        OPENAI = os.getenv("OPENAI_API_KEY")
