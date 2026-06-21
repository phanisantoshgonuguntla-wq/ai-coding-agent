import agent_codegen
import json


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


def test_parse_generated_code_files_reads_file_sections():
    output = """file: snippets/math.py
def add(a, b):
    return a + b

file: snippets/text.py
def shout(text):
    return text.upper()
"""

    files = agent_codegen.parse_generated_code_files(output)

    assert files == [
        {
            "path": "snippets/math.py",
            "code": "def add(a, b):\n    return a + b",
        },
        {
            "path": "snippets/text.py",
            "code": "def shout(text):\n    return text.upper()",
        },
    ]


def test_build_generated_code_files_preview_returns_all_files(monkeypatch, tmp_path):
    def fake_generate_code_files(prompt):
        return """file: snippets/math.py
def add(a, b):
    return a + b

file: snippets/text.py
def shout(text):
    return text.upper()
"""

    monkeypatch.setattr(agent_codegen, "generate_code_files", fake_generate_code_files)

    preview = agent_codegen.build_generated_code_files_preview(
        "write helpers",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is True
    assert preview["has_existing_files"] is False
    assert [file["display_path"] for file in preview["files"]] == [
        "snippets/math.py",
        "snippets/text.py",
    ]
    assert "GENERATED CODE FILES PREVIEW" in preview["output"]
    assert "- workspace/snippets/math.py (create)" in preview["output"]
    assert "- workspace/snippets/text.py (create)" in preview["output"]
    assert not (tmp_path / "snippets" / "math.py").exists()


def test_build_generated_code_files_preview_includes_existing_file_diff(monkeypatch, tmp_path):
    target = tmp_path / "snippets" / "math.py"
    target.parent.mkdir()
    target.write_text("old code\n", encoding="utf-8")

    def fake_generate_code_files(prompt):
        return """file: snippets/math.py
new code
"""

    monkeypatch.setattr(agent_codegen, "generate_code_files", fake_generate_code_files)

    preview = agent_codegen.build_generated_code_files_preview(
        "rewrite helper",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is True
    assert preview["has_existing_files"] is True
    assert "- workspace/snippets/math.py (overwrite)" in preview["output"]
    assert "DIFF:" in preview["output"]
    assert "-old code" in preview["output"]
    assert "+new code" in preview["output"]


def test_build_generated_code_files_preview_rejects_duplicate_paths(monkeypatch, tmp_path):
    def fake_generate_code_files(prompt):
        return """file: snippets/math.py
first

file: snippets/math.py
second
"""

    monkeypatch.setattr(agent_codegen, "generate_code_files", fake_generate_code_files)

    preview = agent_codegen.build_generated_code_files_preview(
        "write duplicate files",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is False
    assert preview["output"] == "Duplicate generated file path: snippets/math.py"


def test_save_code_files_content_writes_all_previewed_files(tmp_path):
    files = [
        {
            "relative_path": "snippets/math.py",
            "code": "def add(a, b):\n    return a + b",
        },
        {
            "relative_path": "snippets/text.py",
            "code": "def shout(text):\n    return text.upper()",
        },
    ]

    output = agent_codegen.save_code_files_content(files, workspace_dir=str(tmp_path))

    assert (tmp_path / "snippets" / "math.py").read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n"
    )
    assert (tmp_path / "snippets" / "text.py").read_text(encoding="utf-8") == (
        "def shout(text):\n    return text.upper()\n"
    )
    assert "CODE FILES SAVED" in output
    assert "workspace/snippets/math.py" in output
    assert "workspace/snippets/text.py" in output


def test_build_project_code_files_preview_uses_project_context(monkeypatch, tmp_path):
    project_path = tmp_path / "demo_app"
    app_file = project_path / "frontend" / "src" / "App.jsx"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("export default function App() { return null; }\n", encoding="utf-8")
    (project_path / "project_spec.json").write_text(
        json.dumps({
            "stack_key": "react_flask_sqlite",
            "app_type": "React + Flask + SQLite",
            "features": ["List customers"],
        }),
        encoding="utf-8",
    )
    prompts = []

    def fake_generate_project_code_files(prompt, project_context):
        prompts.append((prompt, project_context))
        return """file: frontend/src/App.jsx
export default function App() {
    return <h1>Customers</h1>;
}
"""

    monkeypatch.setattr(
        agent_codegen,
        "generate_project_code_files",
        fake_generate_project_code_files,
    )

    preview = agent_codegen.build_project_code_files_preview(
        "demo_app",
        "add a customers heading",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is True
    assert preview["project_name"] == "demo_app"
    assert preview["has_existing_files"] is True
    assert preview["files"][0]["relative_path"].replace("\\", "/") == "demo_app/frontend/src/App.jsx"
    assert "- workspace/demo_app/frontend/src/App.jsx (overwrite)" in preview["output"]
    assert "DIFF:" in preview["output"]
    assert "add a customers heading" in prompts[0][0]
    assert "React + Flask + SQLite" in prompts[0][1]
    assert "frontend/src/App.jsx" in prompts[0][1]


def test_build_project_code_files_preview_rejects_missing_project(tmp_path):
    preview = agent_codegen.build_project_code_files_preview(
        "missing_app",
        "add a heading",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is False
    assert preview["output"] == "Project not found: missing_app"


def test_build_project_code_files_preview_rejects_workspace_prefixed_paths(monkeypatch, tmp_path):
    project_path = tmp_path / "demo_app"
    project_path.mkdir()

    def fake_generate_project_code_files(prompt, project_context):
        return """file: workspace/demo_app/frontend/src/App.jsx
bad path
"""

    monkeypatch.setattr(
        agent_codegen,
        "generate_project_code_files",
        fake_generate_project_code_files,
    )

    preview = agent_codegen.build_project_code_files_preview(
        "demo_app",
        "add a heading",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is False
    assert preview["output"] == "Project-aware generated paths must be relative to the project root."


def test_save_generated_project_code_files_writes_under_project(monkeypatch, tmp_path):
    project_path = tmp_path / "demo_app"
    project_path.mkdir()

    def fake_generate_project_code_files(prompt, project_context):
        return """file: backend/utils.py
def helper():
    return "ok"
"""

    monkeypatch.setattr(
        agent_codegen,
        "generate_project_code_files",
        fake_generate_project_code_files,
    )

    output = agent_codegen.save_generated_project_code_files(
        "demo_app",
        "add backend helper",
        workspace_dir=str(tmp_path),
    )

    saved_file = project_path / "backend" / "utils.py"

    assert saved_file.read_text(encoding="utf-8") == 'def helper():\n    return "ok"\n'
    assert "CODE FILES SAVED" in output
    assert "workspace/demo_app/backend/utils.py" in output


def test_build_project_repair_files_preview_uses_validation_output(monkeypatch, tmp_path):
    project_path = tmp_path / "demo_app"
    app_file = project_path / "backend" / "app.py"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("print('broken')\n", encoding="utf-8")
    prompts = []

    def fake_generate_project_repair_files(prompt, project_context, validation_output):
        prompts.append((prompt, project_context, validation_output))
        return """file: backend/app.py
print("fixed")
"""

    monkeypatch.setattr(
        agent_codegen,
        "generate_project_repair_files",
        fake_generate_project_repair_files,
    )

    preview = agent_codegen.build_project_repair_files_preview(
        "demo_app",
        "add a route",
        "FAIL: backend import failed",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is True
    assert preview["files"][0]["relative_path"].replace("\\", "/") == "demo_app/backend/app.py"
    assert preview["has_existing_files"] is True
    assert preview["output"].startswith("PROJECT REPAIR PREVIEW")
    assert "DIFF:" in preview["output"]
    assert "add a route" in prompts[0][0]
    assert "backend/app.py" in prompts[0][1]
    assert "FAIL: backend import failed" in prompts[0][2]


def test_build_project_repair_files_preview_requires_validation_output(tmp_path):
    project_path = tmp_path / "demo_app"
    project_path.mkdir()

    preview = agent_codegen.build_project_repair_files_preview(
        "demo_app",
        "add a route",
        "",
        workspace_dir=str(tmp_path),
    )

    assert preview["ok"] is False
    assert preview["output"] == "Please provide validation output to repair."


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
