import json
import os
import urllib.request

from langchain_ollama import OllamaLLM


OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")
llm = OllamaLLM(model=OLLAMA_MODEL)


def set_ollama_model(model_name):
    global OLLAMA_MODEL
    global llm

    OLLAMA_MODEL = model_name.strip() or OLLAMA_MODEL
    llm = OllamaLLM(model=OLLAMA_MODEL)
    return OLLAMA_MODEL


def is_ollama_available():
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def get_ollama_models():
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return [
            model.get("name", "")
            for model in payload.get("models", [])
            if model.get("name")
        ]
    except Exception:
        return []


def is_ollama_model_installed(model_name):
    installed_models = get_ollama_models()
    return any(
        model == model_name or model.startswith(f"{model_name}:")
        for model in installed_models
    )


def ollama_unavailable_message():
    return f"""
Ollama is not running or is not reachable.

The agent uses the local Ollama server at:
{OLLAMA_BASE_URL}

Please start Ollama, then try again.

Quick checks:
- Open the Ollama desktop app, or run: ollama serve
- Confirm the model exists: ollama list
- If needed, install the model: ollama pull {OLLAMA_MODEL}

After Ollama is running, refresh Streamlit and rerun your prompt.
"""


def ollama_model_missing_message():
    return f"""
Ollama is running, but the selected model is not installed:
{OLLAMA_MODEL}

Install it with:
ollama pull {OLLAMA_MODEL}

Recommended smaller models for this machine:
- llama3.2:1b
- qwen2.5-coder:1.5b
"""


def ollama_memory_error_message(error_text):
    return f"""
Ollama started, but the selected model does not fit in currently available memory.

Selected model:
{OLLAMA_MODEL}

Error:
{error_text}

Use a smaller model, for example:
ollama pull llama3.2:1b
ollama run llama3.2:1b

Then choose llama3.2:1b in the Streamlit sidebar and retry.
"""


def invoke_llm(prompt):
    if not is_ollama_available():
        raise RuntimeError(ollama_unavailable_message())

    if not is_ollama_model_installed(OLLAMA_MODEL):
        raise RuntimeError(ollama_model_missing_message())

    try:
        return llm.invoke(prompt)
    except Exception as e:
        error_text = str(e)

        if "localhost" in error_text and "11434" in error_text:
            raise RuntimeError(ollama_unavailable_message()) from e

        if "requires more system memory" in error_text:
            raise RuntimeError(ollama_memory_error_message(error_text)) from e

        raise
