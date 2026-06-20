import agent_codegen


def test_generate_code_requires_prompt():
    assert agent_codegen.generate_code("   ") == "Please provide a code generation prompt."


def test_generate_code_invokes_llm_and_cleans_markdown(monkeypatch):
    prompts = []

    def fake_invoke_llm(prompt):
        prompts.append(prompt)
        return "```python\nprint('hello')\n```"

    monkeypatch.setattr(agent_codegen, "invoke_llm", fake_invoke_llm)

    output = agent_codegen.generate_code("write hello world in Python")

    assert output == "print('hello')"
    assert "write hello world in Python" in prompts[0]
    assert "Return code only" in prompts[0]


def test_generate_code_returns_runtime_error_message(monkeypatch):
    def fake_invoke_llm(prompt):
        raise RuntimeError("Ollama is not running")

    monkeypatch.setattr(agent_codegen, "invoke_llm", fake_invoke_llm)

    assert agent_codegen.generate_code("write hello world") == "Ollama is not running"
