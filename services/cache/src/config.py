import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class CACHE:
        # Configuration for future vector database integration
        # For now, just placeholders
        VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "stub")
        TOP_K_DEFAULT = int(os.getenv("CACHE_TOP_K_DEFAULT", "3"))
