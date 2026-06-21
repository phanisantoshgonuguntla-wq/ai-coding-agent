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


def test_save_generated_code_writes_under_workspace(monkeypatch, tmp_path):
    def fake_generate_code(prompt):
        return "def add_numbers(a, b):\n    return a + b"

    monkeypatch.setattr(agent_codegen, "generate_code", fake_generate_code)

    output = agent_codegen.save_generated_code(
        "snippets/math_helpers.py",
        "write add_numbers",
        workspace_dir=str(tmp_path),
    )

    saved_file = tmp_path / "snippets" / "math_helpers.py"

    assert saved_file.read_text(encoding="utf-8") == "def add_numbers(a, b):\n    return a + b\n"
    assert "CODE GENERATED AND SAVED" in output
    assert "workspace/snippets/math_helpers.py" in output


def test_preview_generated_code_reports_target_without_writing(monkeypatch, tmp_path):
    def fake_generate_code(prompt):
        return "def add_numbers(a, b):\n    return a + b"

    monkeypatch.setattr(agent_codegen, "generate_code", fake_generate_code)

    output = agent_codegen.preview_generated_code(
        "snippets/math_helpers.py",
        "write add_numbers",
        workspace_dir=str(tmp_path),
    )

    assert "GENERATED CODE PREVIEW" in output
    assert "workspace/snippets/math_helpers.py" in output
    assert "EXISTS:\nno" in output
    assert "This will create a new file." in output
    assert not (tmp_path / "snippets" / "math_helpers.py").exists()


def test_build_generated_code_preview_returns_saveable_payload(monkeypatch, tmp_path):
    def fake_generate_code(prompt):
        return "def add_numbers(a, b):\n    return a + b"

    monkeypatch.setattr(agent_codegen, "generate_code", fake_generate_code)

    preview = agent_codegen.build_generated_code_preview(
        "snippets/math_helpers.py",
        "write add_numbers",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is True
    assert preview["relative_path"].replace("\\", "/") == "snippets/math_helpers.py"
    assert preview["code"] == "def add_numbers(a, b):\n    return a + b"
    assert "GENERATED CODE PREVIEW" in preview["output"]
    assert not (tmp_path / "snippets" / "math_helpers.py").exists()


def test_save_code_content_writes_exact_preview_code(tmp_path):
    code = "def add_numbers(a, b):\n    return a + b"

    output = agent_codegen.save_code_content(
        "snippets/math_helpers.py",
        code,
        workspace_dir=str(tmp_path),
    )

    saved_file = tmp_path / "snippets" / "math_helpers.py"

    assert saved_file.read_text(encoding="utf-8") == f"{code}\n"
    assert "CODE GENERATED AND SAVED" in output
    assert code in output


def test_preview_generated_code_reports_existing_file(monkeypatch, tmp_path):
    target = tmp_path / "snippets" / "math_helpers.py"
    target.parent.mkdir()
    target.write_text("old code\n", encoding="utf-8")

    def fake_generate_code(prompt):
        return "new code"

    monkeypatch.setattr(agent_codegen, "generate_code", fake_generate_code)

    output = agent_codegen.preview_generated_code(
        "snippets/math_helpers.py",
        "write add_numbers",
        workspace_dir=str(tmp_path),
    )

    assert "EXISTS:\nyes" in output
    assert "This will overwrite the existing file." in output
    assert "DIFF:" in output
    assert "-old code" in output
    assert "+new code" in output
    assert target.read_text(encoding="utf-8") == "old code\n"


def test_preview_generated_code_reports_no_changes(monkeypatch, tmp_path):
    target = tmp_path / "snippets" / "math_helpers.py"
    target.parent.mkdir()
    target.write_text("same code\n", encoding="utf-8")

    def fake_generate_code(prompt):
        return "same code"

    monkeypatch.setattr(agent_codegen, "generate_code", fake_generate_code)

    output = agent_codegen.preview_generated_code(
        "snippets/math_helpers.py",
        "write same code",
        workspace_dir=str(tmp_path),
    )

    assert "DIFF:\nNo changes." in output
    assert target.read_text(encoding="utf-8") == "same code\n"


def test_save_generated_code_rejects_paths_outside_workspace(tmp_path):
    output = agent_codegen.save_generated_code(
        "../outside.py",
        "write unsafe file",
        workspace_dir=str(tmp_path),
    )

    assert output == "File path cannot contain parent directory segments."
    assert not (tmp_path.parent / "outside.py").exists()


def test_save_generated_code_does_not_write_ollama_error(monkeypatch, tmp_path):
    def fake_generate_code(prompt):
        return "Ollama is not running or is not reachable."

    monkeypatch.setattr(agent_codegen, "generate_code", fake_generate_code)

    output = agent_codegen.save_generated_code(
        "snippets/error.py",
        "write code",
        workspace_dir=str(tmp_path),
    )

    assert output == "Ollama is not running or is not reachable."
    assert not (tmp_path / "snippets" / "error.py").exists()
