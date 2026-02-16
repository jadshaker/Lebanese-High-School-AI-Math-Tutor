from openai import OpenAI

from src.config import Config
from src.metrics import embedding_dimensions

# Embedding client (OpenAI API)
embedding_client: OpenAI | None = (
    OpenAI(api_key=Config.API_KEYS.OPENAI) if Config.API_KEYS.OPENAI else None
)

# Set embedding dimensions gauge
embedding_dimensions.set(Config.EMBEDDING.DIMENSIONS)
