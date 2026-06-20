from agent_llm import invoke_llm
from agent_text import clean_code_output


def generate_code(prompt):
    prompt = prompt.strip()

    if not prompt:
        return "Please provide a code generation prompt."

    generation_prompt = f"""
You are a focused coding assistant.

Generate code for this request:
{prompt}

Rules:
- Return code only
- Do not include markdown fences
- Do not include explanations
- Include imports when needed
- Keep the code complete and runnable when possible
"""

    try:
        return clean_code_output(invoke_llm(generation_prompt))
    except RuntimeError as error:
        return str(error)
