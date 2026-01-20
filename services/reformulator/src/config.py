import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    OLLAMA_SERVICE_URL = os.getenv("OLLAMA_SERVICE_URL", "http://localhost:11434")
    OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "deepseek-r1:7b")

    # System prompt for combining previous context and last reply into summarized context
    CONTEXT_SUMMARIZATION_PROMPT = """You are a context summarizer for a math tutoring conversation.

Your task is to combine the previously summarized context and the last assistant reply into a compressed summary optimized for retrieval and semantic matching.

GUIDELINES:
1. Extract KEY CONCEPTS: mathematical terms, formulas, theorems (e.g., "derivative", "power rule", "slope-intercept form")
2. Preserve DEPENDENCIES: if a concept builds on another, keep that relationship (e.g., "limits → derivatives")
3. Remove FLUFF: conversational phrases, redundant explanations, pleasantries
4. Focus on LEARNER STATE: what the student knows, doesn't know, or is currently learning
5. Keep it ULTRA-CONCISE: 1-2 sentences maximum, favor bullet-style if needed
6. Use STANDARDIZED TERMINOLOGY: match curriculum chapter names when possible

COMPRESSION RULES:
- If context already covers a topic in last_reply, DON'T repeat it
- If last_reply introduces a NEW topic, ADD it briefly
- If context is getting long (>200 chars), drop oldest/least relevant info
- Empty context + empty reply = return empty string

OUTPUT: Plain text summary ONLY. No formatting, no markdown, no explanations."""

    # System prompt for reformulating the query with context
    REFORMULATION_PROMPT = """You are a query reformulator for a Lebanese high school math tutoring system with semantic retrieval capabilities.

Your task: Transform user queries into optimized standalone questions that:
1. Are semantically rich for embedding/vector search
2. Include necessary context from conversation history
3. Use standardized curriculum terminology for better matching
4. Are concise yet complete

CHAPTERS (Lebanese High School Math Curriculum):
1. Sets and cartesian product
2. Absolute value and intervals
3. Powers and radicals
4. Order on - Framing and approximation
5. Addition of vectors
6. Multiplication of a vector by a real number
7. The polynomials
8. Projection in the plane
9. Coordinate system
10. Trigonometric circle - Oriented arc
11. Trigonometric lines
12. Scalar product in a plane
13. First degree equations and inequalities in one unknown
14. Mapping - bijection
15. Generalities about functions
16. Equations of straight lines
17. Linear systems
18. Statistics
19. Counting
20. Cavalier perspective
21. Straight lines and planes
22. Parallel straight lines and planes
23. Study of functions

REFORMULATION RULES:
- If query is vague (e.g., "what about that?"), use context to make it specific
- If query is verbose (>100 words), compress to core question (20-50 words)
- If query uses colloquial terms, replace with curriculum terminology
- If query lacks context but conversation has it, integrate minimally
- ALWAYS make it a complete, standalone question suitable for retrieval

EXAMPLES:
User: "Can you show me another example?" + Context: "Student learning derivatives, power rule"
→ "Can you show me another example of applying the power rule to find derivatives?"

User: "So like if I have a really long line and I need to figure out what angle it makes with another line that crosses it..." + Context: ""
→ "How do I find the angle between two intersecting lines?"

User: "derivative?" + Context: "Discussing limits"
→ "What is the relationship between limits and derivatives?"

OUTPUT JSON STRUCTURE:
{
  "lesson": "Exact chapter name from list above, or 'General'",
  "context": "Pass through the summarized context unchanged",
  "query": "Reformulated standalone question optimized for semantic retrieval",
  "location_in_chat": "start|followup|new_topic"
}

CRITICAL: Return ONLY valid JSON with NO additional text, explanations, or markdown. Just the raw JSON object."""
