from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from src.config import Config
from src.models.schemas import GenerateRequest, GenerateResponse

app = FastAPI(title="Math Tutor API Large LLM Service")

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
        "service": "large_llm",
        "model": "gpt-4o-mini",
        "api_configured": api_configured,
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate_answer(request: GenerateRequest):
    """
    Generate answer using OpenAI's GPT-4 API.
    Falls back to dummy response if API key is not configured.
    """
    if not client:
        # Fallback to dummy response if no API key
        answer = f"[Dummy Response] API key not configured. Query: {request.query}"
        return GenerateResponse(
            answer=answer,
            model_used="dummy-fallback",
            confidence=0.5,
        )

    # Build the prompt
    system_prompt = "You are an expert mathematics tutor for Lebanese high school students. Provide clear, accurate, and educational answers to math questions."
    user_message = request.query

    try:
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        answer = response.choices[0].message.content or ""
        model_used = response.model

        return GenerateResponse(
            answer=answer,
            model_used=model_used,
            confidence=0.95,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI API error: {str(e)}",
        )
