import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    FINE_TUNED_MODEL_SERVICE_URL = os.getenv(
        "FINE_TUNED_MODEL_SERVICE_URL", "http://localhost:8006"
    )
    FINE_TUNED_MODEL_NAME = os.environ["FINE_TUNED_MODEL_NAME"]
    FINE_TUNED_MODEL_API_KEY = os.getenv("FINE_TUNED_MODEL_API_KEY", "dummy")
