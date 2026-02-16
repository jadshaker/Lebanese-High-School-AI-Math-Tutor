from openai import OpenAI

from src.config import Config

# Small LLM client (RunPod vLLM)
small_llm_client = OpenAI(
    base_url=f"{Config.SMALL_LLM.SERVICE_URL}/v1",
    api_key=Config.SMALL_LLM.API_KEY,
    timeout=Config.SMALL_LLM.TIMEOUT,
)

# Fine-tuned model client (RunPod vLLM)
fine_tuned_client = OpenAI(
    base_url=f"{Config.FINE_TUNED_MODEL.SERVICE_URL}/v1",
    api_key=Config.FINE_TUNED_MODEL.API_KEY,
    timeout=Config.FINE_TUNED_MODEL.TIMEOUT,
)

# Large LLM client (OpenAI API)
large_llm_client: OpenAI | None = (
    OpenAI(api_key=Config.API_KEYS.OPENAI, timeout=Config.LARGE_LLM.TIMEOUT)
    if Config.API_KEYS.OPENAI
    else None
)

# Reformulator LLM client (RunPod vLLM)
reformulator_client = OpenAI(
    base_url=f"{Config.REFORMULATOR_LLM.SERVICE_URL}/v1",
    api_key=Config.REFORMULATOR_LLM.API_KEY,
    timeout=Config.REFORMULATOR_LLM.TIMEOUT,
)
