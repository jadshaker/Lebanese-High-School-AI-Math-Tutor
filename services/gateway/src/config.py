import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class SERVICES:
        DATA_PROCESSING_URL = os.getenv(
            "DATA_PROCESSING_SERVICE_URL", "http://data-processing:8009"
        )
        ANSWER_RETRIEVAL_URL = os.getenv(
            "ANSWER_RETRIEVAL_SERVICE_URL", "http://answer-retrieval:8008"
        )
