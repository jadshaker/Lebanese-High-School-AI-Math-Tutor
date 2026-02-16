import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    FINE_TUNED_MODEL_SERVICE_URL = os.environ["FINE_TUNED_MODEL_SERVICE_URL"]
    FINE_TUNED_MODEL_NAME = os.environ["FINE_TUNED_MODEL_NAME"]
    FINE_TUNED_MODEL_API_KEY = os.environ["FINE_TUNED_MODEL_API_KEY"]
    FINE_TUNED_MODEL_TIMEOUT = float(os.getenv("FINE_TUNED_MODEL_TIMEOUT", "300"))
