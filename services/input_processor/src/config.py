import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class PROCESSING:
        # Configuration for input processing
        MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "5000"))
        STRIP_WHITESPACE = os.getenv("STRIP_WHITESPACE", "true").lower() == "true"
