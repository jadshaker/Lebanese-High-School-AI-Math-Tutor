import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.config import Config
from src.models.schemas import (
    ChatPhase,
    ChatRequest,
    ChatResponse,
    FinalResponse,
    GatewayHealthResponse,
    QueryRequest,
    RetrievalTier,
    ServiceHealth,
    SessionStateResponse,
    SkipRequest,
)

app = FastAPI(title="Math Tutor API Gateway")

# CORS for UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Service Client Helpers ===


def _call_service(
    url: str,
    method: str = "GET",
    data: Optional[dict[str, Any]] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Generic service caller"""
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode("utf-8") if data else None

    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise HTTPException(status_code=e.code, detail=f"Service error: {error_body}")
    except URLError as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {e.reason}")


def call_session_create(user_id: Optional[str], initial_query: str) -> dict[str, Any]:
    """Create a new session"""
    return _call_service(
        f"{Config.SERVICES.SESSION_URL}/sessions",
        method="POST",
        data={"user_id": user_id, "initial_query": initial_query},
    )


def call_session_get(session_id: str) -> dict[str, Any]:
    """Get session state"""
    return _call_service(f"{Config.SERVICES.SESSION_URL}/sessions/{session_id}")


def call_session_update(session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update session state"""
    return _call_service(
        f"{Config.SERVICES.SESSION_URL}/sessions/{session_id}",
        method="PATCH",
        data=updates,
    )


def call_session_tutoring_update(
    session_id: str, updates: dict[str, Any]
) -> dict[str, Any]:
    """Update tutoring state"""
    return _call_service(
        f"{Config.SERVICES.SESSION_URL}/sessions/{session_id}/tutoring",
        method="PATCH",
        data=updates,
    )


def call_session_add_message(
    session_id: str, role: str, content: str
) -> dict[str, Any]:
    """Add message to session history"""
    return _call_service(
        f"{Config.SERVICES.SESSION_URL}/sessions/{session_id}/messages",
        method="POST",
        data={"role": role, "content": content},
    )


def call_reformulator(
    query: str, previous_context: str = "", last_reply: str = ""
) -> dict[str, Any]:
    """Call reformulator service"""
    return _call_service(
        f"{Config.SERVICES.REFORMULATOR_URL}/reformulate",
        method="POST",
        data={
            "query": query,
            "previous_context": previous_context,
            "last_reply": last_reply,
        },
    )


def call_embedding(text: str) -> dict[str, Any]:
    """Get embedding for text"""
    return _call_service(
        f"{Config.SERVICES.EMBEDDING_URL}/embed",
        method="POST",
        data={"text": text},
    )


def call_vector_search(embedding: list[float], top_k: int = 5) -> dict[str, Any]:
    """Search vector cache"""
    return _call_service(
        f"{Config.SERVICES.VECTOR_CACHE_URL}/search",
        method="POST",
        data={"embedding": embedding, "top_k": top_k, "threshold": 0.3},
    )


def call_vector_add_question(
    question_text: str,
    reformulated_text: str,
    answer_text: str,
    embedding: list[float],
    lesson: Optional[str],
    source: str,
    confidence: float,
) -> dict[str, Any]:
    """Add question to vector cache"""
    return _call_service(
        f"{Config.SERVICES.VECTOR_CACHE_URL}/questions",
        method="POST",
        data={
            "question_text": question_text,
            "reformulated_text": reformulated_text,
            "answer_text": answer_text,
            "embedding": embedding,
            "lesson": lesson,
            "source": source,
            "confidence": confidence,
        },
    )


def call_search_children(
    question_id: str,
    parent_id: Optional[str],
    user_input_embedding: list[float],
    threshold: float = 0.7,
) -> dict[str, Any]:
    """Search for cached interaction by user input similarity"""
    return _call_service(
        f"{Config.SERVICES.VECTOR_CACHE_URL}/interactions/search",
        method="POST",
        data={
            "question_id": question_id,
            "parent_id": parent_id,
            "user_input_embedding": user_input_embedding,
            "threshold": threshold,
        },
    )


def call_add_interaction(
    question_id: str,
    parent_id: Optional[str],
    user_input: str,
    user_input_embedding: list[float],
    system_response: str,
) -> dict[str, Any]:
    """Cache a new interaction (user input + system response)"""
    return _call_service(
        f"{Config.SERVICES.VECTOR_CACHE_URL}/interactions",
        method="POST",
        data={
            "question_id": question_id,
            "parent_id": parent_id,
            "user_input": user_input,
            "user_input_embedding": user_input_embedding,
            "system_response": system_response,
        },
    )


def call_intent_classifier(text: str, context: Optional[str] = None) -> dict[str, Any]:
    """Classify user intent"""
    return _call_service(
        f"{Config.SERVICES.INTENT_CLASSIFIER_URL}/classify",
        method="POST",
        data={"text": text, "context": context},
    )


def call_large_llm(query: str) -> dict[str, Any]:
    """Call large LLM service"""
    return _call_service(
        f"{Config.SERVICES.LARGE_LLM_URL}/generate",
        method="POST",
        data={"query": query},
        timeout=60,
    )


# === Confidence Router ===


def determine_tier(score: float) -> RetrievalTier:
    """Determine confidence tier based on similarity score"""
    if score >= Config.CONFIDENCE.TIER_1_THRESHOLD:
        return RetrievalTier.TIER_1_DIRECT
    elif score >= Config.CONFIDENCE.TIER_2_THRESHOLD:
        return RetrievalTier.TIER_2_VALIDATE
    elif score >= Config.CONFIDENCE.TIER_3_THRESHOLD:
        return RetrievalTier.TIER_3_CONTEXT
    else:
        return RetrievalTier.TIER_4_GENERATE


def route_by_confidence(
    tier: RetrievalTier,
    cached_answer: Optional[str],
    query: str,
) -> tuple[str, str]:
    """Route query based on confidence tier. Returns (answer, source)."""
    if tier == RetrievalTier.TIER_1_DIRECT and cached_answer:
        return cached_answer, "cache"

    elif tier == RetrievalTier.TIER_2_VALIDATE and cached_answer:
        prompt = f"""The user asked: "{query}"
A similar question had this answer: "{cached_answer}"
If appropriate, return it. If it needs adaptation, adapt it. Respond with the answer only."""
        try:
            result = call_large_llm(prompt)
            return result.get("answer", cached_answer), "api_llm"
        except HTTPException:
            return cached_answer, "cache"

    elif tier == RetrievalTier.TIER_3_CONTEXT and cached_answer:
        prompt = f"""The user asked: "{query}"
Context from similar questions: "{cached_answer}"
Use this context to answer. Provide a clear, educational response."""
        try:
            result = call_large_llm(prompt)
            return result.get("answer", ""), "api_llm"
        except HTTPException:
            return cached_answer, "cache"

    else:
        result = call_large_llm(query)
        return result.get("answer", ""), "api_llm"


# === Health Check ===


@app.get("/health", response_model=GatewayHealthResponse)
async def health() -> GatewayHealthResponse:
    """Health check - checks all services"""
    services_to_check = {
        "large_llm": Config.SERVICES.LARGE_LLM_URL,
        "embedding": Config.SERVICES.EMBEDDING_URL,
        "reformulator": Config.SERVICES.REFORMULATOR_URL,
        "vector_cache": Config.SERVICES.VECTOR_CACHE_URL,
        "session": Config.SERVICES.SESSION_URL,
        "intent_classifier": Config.SERVICES.INTENT_CLASSIFIER_URL,
    }

    service_health: dict[str, ServiceHealth] = {}
    all_healthy = True

    for name, url in services_to_check.items():
        try:
            result = _call_service(f"{url}/health", timeout=2)
            service_health[name] = ServiceHealth(
                status=result.get("status", "healthy"), details=result
            )
        except Exception as e:
            service_health[name] = ServiceHealth(status="unhealthy", error=str(e))
            all_healthy = False

    return GatewayHealthResponse(
        status="healthy" if all_healthy else "degraded",
        service="gateway",
        services=service_health,
    )


# === Legacy Endpoint ===


@app.post("/query", response_model=FinalResponse)
async def process_query(request: QueryRequest) -> FinalResponse:
    """Legacy query endpoint - uses large LLM"""
    try:
        llm_response = call_large_llm(request.query)

        return FinalResponse(
            answer=llm_response["answer"],
            path_taken="large_llm",
            verified=True,
            fallback_used=False,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# === Main Chat Pipeline ===


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint implementing the full pipeline:
    1. Create/get session
    2. Reformulate query
    3. Embed query
    4. Search vector cache
    5. Route based on confidence tier
    6. Start tutoring flow (if enabled)
    """
    try:
        # Step 1: Session management
        if request.session_id:
            session = call_session_get(request.session_id)
            session_id = request.session_id

            if session.get("phase") == "tutoring":
                return _handle_tutoring_response(session_id, request.query, session)
        else:
            session_result = call_session_create(request.user_id, request.query)
            session_id = session_result["session_id"]

        call_session_update(
            session_id, {"phase": "reformulation", "original_query": request.query}
        )

        # Step 2: Reformulate query
        try:
            reformulator_result = call_reformulator(request.query)
            reformulated_query = reformulator_result.get(
                "reformulated_query", request.query
            )
            lesson = reformulator_result.get("lesson")
        except HTTPException:
            reformulated_query = request.query
            lesson = None

        call_session_update(
            session_id,
            {
                "phase": "retrieval",
                "reformulated_query": reformulated_query,
                "identified_lesson": lesson,
            },
        )

        # Step 3: Get embedding
        embedding_result = call_embedding(reformulated_query)
        embedding = embedding_result["embedding"]

        # Step 4: Search vector cache
        search_result = call_vector_search(embedding, top_k=3)
        results = search_result.get("results", [])

        # Step 5: Confidence routing
        question_id: Optional[str] = None
        if results:
            top_result = results[0]
            score = top_result["score"]
            cached_answer = top_result["answer_text"]
            question_id = top_result["id"]  # Use cached question's ID
            tier = determine_tier(score)
        else:
            score = 0.0
            cached_answer = None
            tier = RetrievalTier.TIER_4_GENERATE

        answer, source = route_by_confidence(tier, cached_answer, reformulated_query)

        call_session_update(
            session_id,
            {
                "retrieved_answer": answer,
                "retrieval_score": score,
                "retrieval_source": source,
            },
        )

        # Step 6: Cache if new question (no good match found)
        if tier == RetrievalTier.TIER_4_GENERATE and answer:
            try:
                cache_result = call_vector_add_question(
                    question_text=request.query,
                    reformulated_text=reformulated_query,
                    answer_text=answer,
                    embedding=embedding,
                    lesson=lesson,
                    source=source,
                    confidence=0.8,
                )
                question_id = cache_result.get("id")
            except HTTPException:
                pass

        # Step 7: Start tutoring or return answer
        # Tutoring now uses incremental caching - no pre-generated graph needed
        if Config.TUTORING.ENABLE_TUTORING and question_id:
            return _start_tutoring_flow(
                session_id, question_id, answer, score, tier, source, lesson
            )

        call_session_update(session_id, {"phase": "completed"})
        call_session_add_message(session_id, "assistant", answer)

        return ChatResponse(
            session_id=session_id,
            phase=ChatPhase.COMPLETED,
            message=answer,
            retrieval_score=score,
            retrieval_tier=tier,
            source=source,
            final_answer=answer,
            lesson=lesson,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


def _start_tutoring_flow(
    session_id: str,
    question_id: str,
    answer: str,
    score: float,
    tier: RetrievalTier,
    source: str,
    lesson: Optional[str],
) -> ChatResponse:
    """Start the tutoring flow with a diagnostic question.

    Instead of giving the answer directly, we:
    1. Generate a diagnostic question to check understanding
    2. Guide the student through the problem
    3. Only reveal the answer at the end (or if they skip)
    """
    original_query = call_session_get(session_id).get("original_query", "")

    # Generate a diagnostic/tutoring question
    prompt = f"""You are a math tutor. A student asked: "{original_query}"

Instead of giving the answer directly, ask ONE diagnostic question to check if they understand a key concept needed to solve this problem.

For example, if the problem involves integration, you might ask "Do you know the power rule for integration?" or "What happens when you integrate x^n?"

Keep the question short (1-2 sentences). Don't give hints about the answer yet."""

    try:
        llm_result = call_large_llm(prompt)
        tutoring_question = llm_result.get("answer", "Let's work through this step by step. What concept do you think we need to apply here?")
    except HTTPException:
        tutoring_question = "Let's work through this step by step. What concept do you think we need to apply here?"

    call_session_update(session_id, {"phase": "tutoring"})
    call_session_tutoring_update(
        session_id,
        {
            "question_id": question_id,
            "current_node_id": None,  # No node yet - at question root
            "depth": 0,
        },
    )
    call_session_add_message(session_id, "assistant", tutoring_question)

    return ChatResponse(
        session_id=session_id,
        phase=ChatPhase.TUTORING,
        message=tutoring_question,
        retrieval_score=score,
        retrieval_tier=tier,
        source=source,
        tutoring_depth=0,
        can_skip=True,
        final_answer=answer,  # Hidden from user, revealed on skip/completion
        lesson=lesson,
    )


def _handle_tutoring_response(
    session_id: str, user_response: str, session: dict[str, Any]
) -> ChatResponse:
    """Handle user's response during tutoring flow.

    Uses incremental caching:
    - Search for similar user inputs among children of current node
    - Cache hit: return cached system_response
    - Cache miss: generate with LLM, cache the new interaction
    """
    tutoring = session.get("tutoring", {})
    question_id = tutoring.get("question_id")
    current_node_id = tutoring.get("current_node_id")  # None if at question root
    depth = tutoring.get("depth", 0)
    answer = session.get("retrieved_answer", "")
    lesson = session.get("identified_lesson")
    original_query = session.get("original_query", "")

    if not question_id:
        call_session_update(session_id, {"phase": "completed"})
        return ChatResponse(
            session_id=session_id,
            phase=ChatPhase.COMPLETED,
            message=answer,
            final_answer=answer,
            lesson=lesson,
        )

    call_session_add_message(session_id, "user", user_response)

    # Classify intent for skip detection
    try:
        intent_result = call_intent_classifier(user_response)
        intent = intent_result.get("intent", "off_topic")
    except HTTPException:
        intent = "partial"

    if intent == "skip":
        return _skip_tutoring(session_id, answer, lesson)

    # Get embedding of user's response
    try:
        embedding_result = call_embedding(user_response)
        user_embedding = embedding_result["embedding"]
    except HTTPException:
        # Can't proceed without embedding
        call_session_update(session_id, {"phase": "completed"})
        return ChatResponse(
            session_id=session_id,
            phase=ChatPhase.COMPLETED,
            message=answer,
            final_answer=answer,
            lesson=lesson,
        )

    # Search for cached interaction with similar user input
    try:
        search_result = call_search_children(
            question_id=question_id,
            parent_id=current_node_id,
            user_input_embedding=user_embedding,
            threshold=0.7,
        )
    except HTTPException:
        search_result = {"is_cache_hit": False}

    new_depth = depth + 1

    if search_result.get("is_cache_hit"):
        # Cache hit - use cached response
        matched_node = search_result.get("matched_node", {})
        response_content = matched_node.get("system_response", "")
        next_node_id = matched_node.get("id")

        call_session_tutoring_update(
            session_id,
            {"current_node_id": next_node_id, "depth": new_depth},
        )
        call_session_add_message(session_id, "assistant", response_content)

        if new_depth >= Config.TUTORING.MAX_DEPTH:
            call_session_update(session_id, {"phase": "completed"})
            return ChatResponse(
                session_id=session_id,
                phase=ChatPhase.COMPLETED,
                message=response_content,
                final_answer=answer,
                tutoring_depth=new_depth,
                lesson=lesson,
            )

        return ChatResponse(
            session_id=session_id,
            phase=ChatPhase.TUTORING,
            message=response_content,
            tutoring_depth=new_depth,
            can_skip=True,
            final_answer=answer,
            lesson=lesson,
        )

    else:
        # Cache miss - generate with LLM
        # IMPORTANT: Only give ONE step at a time, not the full solution
        prompt = f"""You are a Socratic math tutor helping a student understand: "{original_query}"

You know the answer is: "{answer}"
BUT DO NOT REVEAL THE FULL SOLUTION.

The student just said: "{user_response}"

Your task:
1. Address what they said (if they're confused, explain ONLY the concept they asked about)
2. Give them ONE small hint or explain ONE step
3. End with a follow-up question to check their understanding or guide them to the next step

Keep your response SHORT (2-4 sentences max). Do NOT solve the whole problem for them."""

        try:
            llm_result = call_large_llm(prompt)
            generated = llm_result.get("answer", "")
        except HTTPException:
            generated = f"Let me help clarify. {answer}"

        # Cache this new interaction for future use
        new_node_id = None
        try:
            cache_result = call_add_interaction(
                question_id=question_id,
                parent_id=current_node_id,
                user_input=user_response,
                user_input_embedding=user_embedding,
                system_response=generated,
            )
            new_node_id = cache_result.get("id")
        except HTTPException:
            pass  # Caching failed, but we can still return the response

        call_session_tutoring_update(
            session_id,
            {"current_node_id": new_node_id, "depth": new_depth},
        )
        call_session_add_message(session_id, "assistant", generated)

        if new_depth >= Config.TUTORING.MAX_DEPTH:
            call_session_update(session_id, {"phase": "completed"})
            return ChatResponse(
                session_id=session_id,
                phase=ChatPhase.COMPLETED,
                message=generated,
                final_answer=answer,
                tutoring_depth=new_depth,
                lesson=lesson,
            )

        return ChatResponse(
            session_id=session_id,
            phase=ChatPhase.TUTORING,
            message=generated,
            tutoring_depth=new_depth,
            can_skip=True,
            final_answer=answer,
            lesson=lesson,
        )


# === Tutoring Control ===


@app.post("/chat/{session_id}/skip", response_model=ChatResponse)
async def skip_tutoring(session_id: str, request: SkipRequest) -> ChatResponse:
    """Skip tutoring and get the answer directly"""
    try:
        session = call_session_get(session_id)
        answer = session.get("retrieved_answer", "")
        lesson = session.get("identified_lesson")
        return _skip_tutoring(session_id, answer, lesson)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


def _skip_tutoring(session_id: str, answer: str, lesson: Optional[str]) -> ChatResponse:
    """Skip tutoring and return answer"""
    call_session_update(session_id, {"phase": "completed"})
    call_session_add_message(session_id, "assistant", answer)

    return ChatResponse(
        session_id=session_id,
        phase=ChatPhase.COMPLETED,
        message=answer,
        final_answer=answer,
        can_skip=False,
        lesson=lesson,
    )


@app.get("/chat/{session_id}", response_model=SessionStateResponse)
async def get_session_state(session_id: str) -> SessionStateResponse:
    """Get current state of a chat session"""
    try:
        session = call_session_get(session_id)
        tutoring = session.get("tutoring", {})

        phase_map = {
            "initial": ChatPhase.PROCESSING,
            "reformulation": ChatPhase.PROCESSING,
            "retrieval": ChatPhase.PROCESSING,
            "tutoring": ChatPhase.TUTORING,
            "completed": ChatPhase.COMPLETED,
        }
        phase = phase_map.get(session.get("phase", "initial"), ChatPhase.PROCESSING)

        return SessionStateResponse(
            session_id=session_id,
            phase=phase,
            original_query=session.get("original_query"),
            reformulated_query=session.get("reformulated_query"),
            lesson=session.get("identified_lesson"),
            retrieved_answer=session.get("retrieved_answer"),
            retrieval_score=session.get("retrieval_score"),
            tutoring_depth=tutoring.get("depth", 0),
            current_node_id=tutoring.get("current_node_id"),
            message_count=session.get("message_count", 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
