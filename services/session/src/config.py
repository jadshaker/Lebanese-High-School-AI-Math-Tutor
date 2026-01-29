import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SESSION:
        TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))  # 1 hour default
        MAX_HISTORY_LENGTH = int(os.getenv("SESSION_MAX_HISTORY", "50"))

    class CLEANUP:
        INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))  # 5 min
