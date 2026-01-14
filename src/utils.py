import os
import dspy
from typing import Literal
from constants import (
    OLLAMA_MODEL,
    OLLAMA_OPENAI_BASE_URL,
    OLLAMA_OPENAI_API_KEY,
)
GOOGLE_PROVIDER_GEMINI = "gemini"
GOOGLE_PROVIDER_VERTEX_AI = "vertex_ai"
GOOGLE_PROVIDER_LIST = [GOOGLE_PROVIDER_GEMINI, GOOGLE_PROVIDER_VERTEX_AI]

def indent(text: str, prefix: str = "  ") -> str:
    """Indent each non-empty line in `text` with `prefix`."""
    return "\n".join((prefix + line) if line.strip() else line for line in str(text).splitlines())

def get_model_access_prefix_or_fail(model_name: str) -> str:
    """
    Whenever the model name already contains the access prefix then look up if the env variables are set and return the access prefix.
    In case the model name does not contain the access prefix then decide from the env variables what access prefix to return.
    When no prefix is specified, vertex_ai/ is prioritized if available.

    Returns e.g. "" or "gemini/" or "vertex_ai/"
    """
    provider_from_model_name: str | None = model_name.split("/")[0] if "/" in model_name else None
    if provider_from_model_name is not None and provider_from_model_name not in GOOGLE_PROVIDER_LIST:
        return "" # In this case the model name already contains the provider and it is one we use as is

    # Collect state: what credentials are available
    has_vertex_ai_env_vars = os.getenv("VERTEXAI_PROJECT") and os.getenv("VERTEXAI_LOCATION")
    has_gemini_env_vars = os.getenv("GEMINI_API_KEY")
    
    selected_provider: str | None = None
    # Evaluate based on model name and available credentials
    if provider_from_model_name is not None and provider_from_model_name == GOOGLE_PROVIDER_VERTEX_AI:
        if not has_vertex_ai_env_vars:
            raise ValueError(f"Both VERTEXAI_PROJECT and VERTEXAI_LOCATION must be set as environment variables for {GOOGLE_PROVIDER_VERTEX_AI} prefix")
        selected_provider = provider_from_model_name
    elif provider_from_model_name is not None and provider_from_model_name == GOOGLE_PROVIDER_GEMINI:
        if not has_gemini_env_vars:
            raise ValueError(f"GEMINI_API_KEY must be set as environment variable for {GOOGLE_PROVIDER_GEMINI} prefix")
        selected_provider = provider_from_model_name
    
    # No explicit prefix - decide based on available credentials
    if not selected_provider:
        if has_vertex_ai_env_vars:
            selected_provider = GOOGLE_PROVIDER_VERTEX_AI
        elif has_gemini_env_vars:
            selected_provider = GOOGLE_PROVIDER_GEMINI
        else:
            raise ValueError("Either (VERTEXAI_PROJECT and VERTEXAI_LOCATION) or (GEMINI_API_KEY) must be set as environment variables.")
    
    # Unset the other env vars to have clarity
    if selected_provider == GOOGLE_PROVIDER_VERTEX_AI:
        os.unsetenv("GEMINI_API_KEY")
    elif selected_provider == GOOGLE_PROVIDER_GEMINI:
        os.unsetenv("VERTEXAI_PROJECT")
        os.unsetenv("VERTEXAI_LOCATION")

    # finished preparing
    print(f"Using model access prefix: {selected_provider}")
    return f"{selected_provider}/"

def dspy_configure(lm: dspy.LM, track_usage: bool = True, adapter: dspy.Adapter = dspy.JSONAdapter()):
    """
    Using JSONAdapter as it is the most reliable adapter from tests.
    XMLAdapter and ChatAdapter force retries using JSONAdapter as fallback anyways.
    """
    dspy.settings.configure(lm=lm, track_usage=track_usage, adapter=adapter)
    dspy.configure_cache(enable_disk_cache=False, enable_memory_cache=False)

def get_lm_for_model_name(model_name: str, reasoning_effort: Literal["low", "medium", "high", "disable"] | None = "disable", max_tokens: int = 8192, temperature: float = 0.3) -> dspy.LM:
    model_access_prefix: str = get_model_access_prefix_or_fail(model_name)
    return dspy.LM(
        model=f'{model_access_prefix}{model_name}',
        max_tokens=max_tokens, temperature=temperature,
        reasoning_effort=reasoning_effort if reasoning_effort is not None else None,
        # thinking={"type": "enabled", "budget_tokens": 512}
    )

def get_lm_for_ollama(
    model_name: str | None = None,
    api_base_url: str | None = None,
    api_key: str | None = None,
    reasoning_effort: Literal["low", "medium", "high", "disable"] | None = "disable",
    max_tokens: int = 8192,
    temperature: float = 0.3
) -> dspy.LM:
    """
    Get DSPy LM for Ollama using OpenAI-compatible API.
    
    Args:
        model_name: Ollama model name (defaults to OLLAMA_MODEL from constants)
        api_base_url: Base URL for OpenAI-compatible API (defaults to OLLAMA_OPENAI_BASE_URL)
        api_key: API key placeholder (defaults to OLLAMA_OPENAI_API_KEY)
        reasoning_effort: Reasoning effort level
        max_tokens: Maximum tokens
        temperature: Temperature setting
    """
    selected_model = model_name if model_name else OLLAMA_MODEL
    selected_base_url = api_base_url if api_base_url else OLLAMA_OPENAI_BASE_URL
    selected_api_key = api_key if api_key else OLLAMA_OPENAI_API_KEY
    
    # Set environment variables for OpenAI-compatible API
    os.environ["OPENAI_API_KEY"] = selected_api_key
    os.environ["OPENAI_BASE_URL"] = selected_base_url
    # Use the root base URL (without /v1) for Ollama provider
    if selected_base_url.endswith("/v1"):
        os.environ["OLLAMA_BASE_URL"] = selected_base_url[:-3]
    else:
        os.environ["OLLAMA_BASE_URL"] = selected_base_url
    
    return dspy.LM(
        model=f"ollama/{selected_model}",
        max_tokens=max_tokens,
        temperature=temperature,
        reasoning_effort=reasoning_effort if reasoning_effort is not None else None,
    )