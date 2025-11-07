import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class API_KEYS:
        OPENAI = os.getenv("OPENAI_API_KEY")

    class EMBEDDING:
        MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
