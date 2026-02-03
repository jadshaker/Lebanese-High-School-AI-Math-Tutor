import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SESSION:
        TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
        MAX_HISTORY_LENGTH = int(os.getenv("SESSION_MAX_HISTORY", "50"))

    class CLEANUP:
        INTERVAL_SECONDS = int(os.getenv("SESSION_CLEANUP_INTERVAL", "300"))
