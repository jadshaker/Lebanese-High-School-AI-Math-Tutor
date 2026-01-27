import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    FINE_TUNED_MODEL_SERVICE_URL = os.getenv(
        "FINE_TUNED_MODEL_SERVICE_URL", "http://localhost:11434"
    )
    FINE_TUNED_MODEL_NAME = os.environ["FINE_TUNED_MODEL_NAME"]
