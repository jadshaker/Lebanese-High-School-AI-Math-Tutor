import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    class QDRANT:
        HOST = os.getenv("QDRANT_HOST", "localhost")
        PORT = int(os.getenv("QDRANT_PORT", "6333"))
        GRPC_PORT = int(os.getenv("QDRANT_GRPC_PORT", "6334"))

    class COLLECTIONS:
        QUESTIONS = "questions"
        TUTORING_NODES = "tutoring_nodes"

    class VECTOR:
        DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
        DISTANCE = "Cosine"

    class SEARCH:
        DEFAULT_TOP_K = int(os.getenv("CACHE_TOP_K", "5"))
        DEFAULT_THRESHOLD = 0.5
        HIGH_CONFIDENCE_THRESHOLD = 0.9
        MEDIUM_CONFIDENCE_THRESHOLD = 0.7

    class GRAPH:
        MAX_DEPTH = int(os.getenv("TUTORING_MAX_DEPTH", "4"))
        MAX_CHILDREN_PER_NODE = 5
