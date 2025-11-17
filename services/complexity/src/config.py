import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    COMPLEXITY_THRESHOLD = float(os.getenv("COMPLEXITY_THRESHOLD", "0.5"))
