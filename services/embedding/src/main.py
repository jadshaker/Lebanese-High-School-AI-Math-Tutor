from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from src.config import Config
from src.models.schemas import EmbedRequest, EmbedResponse

app = FastAPI(title="Math Tutor API Embedding Service")

# CORS for UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
client = OpenAI(api_key=Config.API_KEYS.OPENAI) if Config.API_KEYS.OPENAI else None


@app.get("/health")
async def health():
    """Health check endpoint"""
    api_configured = Config.API_KEYS.OPENAI is not None
    return {
        "status": "healthy",
        "service": "embedding",
        "model": Config.EMBEDDING.MODEL,
        "dimensions": Config.EMBEDDING.DIMENSIONS,
        "api_configured": api_configured,
    }


@app.post("/embed", response_model=EmbedResponse)
async def embed_text(request: EmbedRequest):
    """
    Generate embedding for input text using OpenAI's embedding API.
    Falls back to dummy response if API key is not configured.
    """
    if not client:
        # Fallback to dummy response if no API key
        dummy_embedding = [0.0] * Config.EMBEDDING.DIMENSIONS
        return EmbedResponse(
            embedding=dummy_embedding,
            model="dummy-fallback",
            dimensions=Config.EMBEDDING.DIMENSIONS,
        )

    try:
        # Call OpenAI Embeddings API
        response = client.embeddings.create(
            model=Config.EMBEDDING.MODEL,
            input=request.text,
            dimensions=Config.EMBEDDING.DIMENSIONS,
        )

        embedding = response.data[0].embedding
        model_used = response.model

        return EmbedResponse(
            embedding=embedding,
            model=model_used,
            dimensions=len(embedding),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI Embeddings API error: {str(e)}",
        )
