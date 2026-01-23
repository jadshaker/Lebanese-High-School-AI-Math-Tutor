import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        INPUT_PROCESSOR_URL = os.getenv(
            "INPUT_PROCESSOR_SERVICE_URL", "http://input-processor:8004"
        )
        REFORMULATOR_URL = os.getenv(
            "REFORMULATOR_SERVICE_URL", "http://reformulator:8007"
        )
