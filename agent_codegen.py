import difflib
import json
import os
import re

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


def generate_code_files(prompt):
    prompt = prompt.strip()

    if not prompt:
        return "Please provide a multi-file code generation prompt."

    generation_prompt = f"""
You are a focused coding assistant.

Generate one or more complete code files for this request:
{prompt}

STRICT OUTPUT FORMAT:

file: path/to/file.ext
<complete file contents>

file: path/to/another_file.ext
<complete file contents>

Rules:
- Return only file sections
- Every file MUST start with: file: <relative_path>
- Do not include markdown fences
- Do not include explanations
- Use relative paths only
- Include imports when needed
- Keep each file complete and runnable when possible
"""

    try:
        return clean_code_output(invoke_llm(generation_prompt))
    except RuntimeError as error:
        return str(error)


def generate_project_code_files(prompt, project_context):
    prompt = prompt.strip()

    if not prompt:
        return "Please provide a project-aware code generation prompt."

    generation_prompt = f"""
You are a focused coding assistant modifying an existing generated project.

Project context:
{project_context}

User request:
{prompt}

STRICT OUTPUT FORMAT:

file: relative/path/inside/project.ext
<complete file contents>

file: another/relative/path/inside/project.ext
<complete file contents>

Rules:
- Return only file sections
- Every file MUST start with: file: <relative_path>
- Paths must be relative to the selected project root
- Do not prefix paths with workspace/ or the project name
- Do not include markdown fences
- Do not include explanations
- Include complete replacement file contents
- Preserve the project's stack, ports, API URLs, and existing conventions
"""

    try:
        return clean_code_output(invoke_llm(generation_prompt))
    except RuntimeError as error:
        return str(error)


def _normalize_workspace_path(file_path, workspace_dir):
    file_path = file_path.strip().replace("\\", "/")

    if file_path.startswith("workspace/"):
        file_path = file_path[len("workspace/"):]

    if not file_path:
        raise ValueError("Please provide a file path under workspace/.")

    if os.path.isabs(file_path):
        raise ValueError("Use a relative path under workspace/, not an absolute path.")

    normalized_path = os.path.normpath(file_path)
    path_parts = normalized_path.replace("\\", "/").split("/")

    if normalized_path in [".", ""] or ".." in path_parts:
        raise ValueError("File path cannot contain parent directory segments.")

    if os.path.basename(normalized_path) == "":
        raise ValueError("Please provide a file name, not only a folder.")

    workspace_root = os.path.abspath(workspace_dir)
    target_path = os.path.abspath(os.path.join(workspace_root, normalized_path))

    if os.path.commonpath([workspace_root, target_path]) != workspace_root:
        raise ValueError("File path must stay inside workspace/.")

    return normalized_path, target_path


def _looks_like_generation_error(text):
    return text.lstrip().startswith("Ollama ")


def _load_project_spec(project_path):
    spec_path = os.path.join(project_path, "project_spec.json")

    if not os.path.exists(spec_path):
        return {}

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _read_context_file(project_path, relative_path, max_chars=4000):
    file_path = os.path.join(project_path, relative_path)

    if not os.path.exists(file_path):
        return ""

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read(max_chars)
    except Exception:
        return ""

    return f"""
--- {relative_path} ---
{content}
"""


def build_project_context(project_name, workspace_dir="workspace"):
    project_name = project_name.strip()

    if not project_name:
        return {
            "ok": False,
            "error": "Please provide a project name.",
            "output": "Please provide a project name.",
        }

    workspace_root = os.path.abspath(workspace_dir)
    project_path = os.path.abspath(os.path.join(workspace_root, project_name))

    if os.path.commonpath([workspace_root, project_path]) != workspace_root:
        return {
            "ok": False,
            "error": "Project path must stay inside workspace/.",
            "output": "Project path must stay inside workspace/.",
        }

    if not os.path.isdir(project_path):
        return {
            "ok": False,
            "error": f"Project not found: {project_name}",
            "output": f"Project not found: {project_name}",
        }

    spec = _load_project_spec(project_path)
    stack_key = spec.get("stack_key", "unknown")
    stack_label = spec.get("app_type", stack_key)
    context_files = [
        "project_spec.json",
        "project_config.json",
        "backend/app.py",
        "backend/routes.py",
        "backend/models.py",
        "backend/database.py",
        "backend/Program.cs",
        "backend/index.php",
        "backend/database.php",
        "frontend/package.json",
        "frontend/src/App.jsx",
        "frontend/src/api.js",
        "frontend/src/style.css",
    ]
    file_context = "".join(
        _read_context_file(project_path, relative_path)
        for relative_path in context_files
    ).strip()
    spec_summary = json.dumps(spec, indent=2) if spec else "{}"

    return {
        "ok": True,
        "project_name": project_name,
        "project_path": project_path,
        "stack_key": stack_key,
        "stack_label": stack_label,
        "context": f"""
PROJECT:
{project_name}

STACK:
{stack_label}

PROJECT SPEC:
{spec_summary}

RELEVANT FILES:
{file_context or "No recognized context files found."}
""".strip(),
    }


def parse_generated_code_files(text):
    files = []
    current_path = None
    current_lines = []

    for line in text.splitlines():
        match = re.match(r"^\s*file:\s*(.+?)\s*$", line, flags=re.IGNORECASE)

        if match:
            if current_path is not None:
                files.append({
                    "path": current_path,
                    "code": "\n".join(current_lines).strip(),
                })

            current_path = match.group(1).strip()
            current_lines = []
            continue

        if current_path is not None:
            current_lines.append(line)

    if current_path is not None:
        files.append({
            "path": current_path,
            "code": "\n".join(current_lines).strip(),
        })

    return [
        file
        for file in files
        if file["path"] and file["code"]
    ]


def _format_preview(relative_path, target_path, code):
    display_path = relative_path.replace("\\", "/")
    exists = os.path.exists(target_path)
    action = "overwrite the existing file" if exists else "create a new file"
    preview_sections = [
        "GENERATED CODE PREVIEW",
        "",
        "FILE:",
        f"workspace/{display_path}",
        "",
        "EXISTS:",
        "yes" if exists else "no",
        "",
        "ACTION:",
        f"This will {action}.",
    ]

    if exists:
        with open(target_path, "r", encoding="utf-8") as f:
            current_code = f.read()

        diff = "".join(
            difflib.unified_diff(
                current_code.splitlines(keepends=True),
                f"{code}\n".splitlines(keepends=True),
                fromfile=f"workspace/{display_path} (current)",
                tofile=f"workspace/{display_path} (generated)",
            )
        ).strip()

        preview_sections.extend(["", "DIFF:", diff or "No changes."])

    preview_sections.extend(["", "CODE:", code])

    return "\n".join(preview_sections)


def build_generated_code_preview(file_path, prompt, workspace_dir="workspace"):
    prompt = prompt.strip()

    if not prompt:
        return {
            "ok": False,
            "error": "Please provide a code generation prompt.",
            "output": "Please provide a code generation prompt.",
        }

    try:
        relative_path, target_path = _normalize_workspace_path(file_path, workspace_dir)
    except ValueError as error:
        return {
            "ok": False,
            "error": str(error),
            "output": str(error),
        }

    code = generate_code(prompt)

    if _looks_like_generation_error(code):
        return {
            "ok": False,
            "error": code,
            "output": code,
        }

    return {
        "ok": True,
        "relative_path": relative_path,
        "target_path": target_path,
        "exists": os.path.exists(target_path),
        "code": code,
        "output": _format_preview(relative_path, target_path, code),
    }


def _format_multi_file_preview(entries):
    summary_lines = [
        "GENERATED CODE FILES PREVIEW",
        "",
        "FILES:",
    ]

    for entry in entries:
        status = "overwrite" if entry["exists"] else "create"
        summary_lines.append(f"- workspace/{entry['display_path']} ({status})")

    file_sections = [
        _format_preview(
            entry["relative_path"],
            entry["target_path"],
            entry["code"],
        )
        for entry in entries
    ]

    return "\n".join(summary_lines + ["", "====================", ""] + [
        "\n\n====================\n\n".join(file_sections)
    ])


def _build_code_files_preview_from_files(files, workspace_dir):
    entries = []
    seen_paths = set()

    for file in files:
        try:
            relative_path, target_path = _normalize_workspace_path(
                file["path"],
                workspace_dir,
            )
        except ValueError as error:
            return {
                "ok": False,
                "error": str(error),
                "output": str(error),
            }

        normalized_key = relative_path.replace("\\", "/").lower()

        if normalized_key in seen_paths:
            return {
                "ok": False,
                "error": f"Duplicate generated file path: {file['path']}",
                "output": f"Duplicate generated file path: {file['path']}",
            }

        seen_paths.add(normalized_key)
        entries.append({
            "relative_path": relative_path,
            "display_path": relative_path.replace("\\", "/"),
            "target_path": target_path,
            "exists": os.path.exists(target_path),
            "code": file["code"],
        })

    return {
        "ok": True,
        "files": entries,
        "has_existing_files": any(entry["exists"] for entry in entries),
        "output": _format_multi_file_preview(entries),
    }


def build_generated_code_files_preview(prompt, workspace_dir="workspace"):
    prompt = prompt.strip()

    if not prompt:
        return {
            "ok": False,
            "error": "Please provide a multi-file code generation prompt.",
            "output": "Please provide a multi-file code generation prompt.",
        }

    generated_output = generate_code_files(prompt)

    if _looks_like_generation_error(generated_output):
        return {
            "ok": False,
            "error": generated_output,
            "output": generated_output,
        }

    files = parse_generated_code_files(generated_output)

    if not files:
        return {
            "ok": False,
            "error": "No file sections were generated.",
            "output": (
                "No file sections were generated. "
                "Expected format: file: path/to/file.ext"
            ),
        }

    return _build_code_files_preview_from_files(files, workspace_dir)


def build_project_code_files_preview(project_name, prompt, workspace_dir="workspace"):
    prompt = prompt.strip()

    if not prompt:
        return {
            "ok": False,
            "error": "Please provide a project-aware code generation prompt.",
            "output": "Please provide a project-aware code generation prompt.",
        }

    context = build_project_context(project_name, workspace_dir)

    if not context["ok"]:
        return context

    generated_output = generate_project_code_files(prompt, context["context"])

    if _looks_like_generation_error(generated_output):
        return {
            "ok": False,
            "error": generated_output,
            "output": generated_output,
        }

    files = parse_generated_code_files(generated_output)

    if not files:
        return {
            "ok": False,
            "error": "No file sections were generated.",
            "output": (
                "No file sections were generated. "
                "Expected format: file: path/to/file.ext"
            ),
        }

    project_name_for_path = context["project_name"].replace("\\", "/")
    project_prefix = f"{project_name_for_path}/".lower()

    for file in files:
        generated_path = file["path"].replace("\\", "/").lower()

        if generated_path.startswith("workspace/") or generated_path.startswith(project_prefix):
            return {
                "ok": False,
                "error": "Project-aware generated paths must be relative to the project root.",
                "output": "Project-aware generated paths must be relative to the project root.",
            }

    project_workspace = os.path.join(workspace_dir, context["project_name"])
    preview = _build_code_files_preview_from_files(files, project_workspace)

    if not preview["ok"]:
        return preview

    for file in preview["files"]:
        file["project_relative_path"] = file["relative_path"]
        file["relative_path"] = os.path.join(
            context["project_name"],
            file["project_relative_path"],
        )
        file["display_path"] = file["relative_path"].replace("\\", "/")

    return {
        "ok": True,
        "project_name": context["project_name"],
        "files": preview["files"],
        "has_existing_files": preview["has_existing_files"],
        "output": _format_multi_file_preview(preview["files"]),
    }


def preview_generated_code(file_path, prompt, workspace_dir="workspace"):
    return build_generated_code_preview(file_path, prompt, workspace_dir)["output"]


def preview_generated_code_files(prompt, workspace_dir="workspace"):
    return build_generated_code_files_preview(prompt, workspace_dir)["output"]


def preview_project_code_files(project_name, prompt, workspace_dir="workspace"):
    return build_project_code_files_preview(project_name, prompt, workspace_dir)["output"]


def save_code_content(file_path, code, workspace_dir="workspace"):
    if not code.strip():
        return "Please preview generated code before saving."

    try:
        relative_path, target_path = _normalize_workspace_path(file_path, workspace_dir)
    except ValueError as error:
        return str(error)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(code)
        f.write("\n")

    display_path = relative_path.replace("\\", "/")

    return f"""CODE GENERATED AND SAVED

FILE:
workspace/{display_path}

CODE:
{code}
"""


def save_code_files_content(files, workspace_dir="workspace"):
    if not files:
        return "Please preview generated code files before saving."

    saved_paths = []

    for file in files:
        code = file.get("code", "")

        if not code.strip():
            return "Generated file content cannot be empty."

        try:
            relative_path, target_path = _normalize_workspace_path(
                file["relative_path"],
                workspace_dir,
            )
        except ValueError as error:
            return str(error)

        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(code)
            f.write("\n")

        display_path = relative_path.replace("\\", "/")
        saved_paths.append(f"workspace/{display_path}")

    return f"""CODE FILES SAVED

FILES:
{chr(10).join(saved_paths)}
"""


def save_generated_code(file_path, prompt, workspace_dir="workspace"):
    preview = build_generated_code_preview(file_path, prompt, workspace_dir)

    if not preview["ok"]:
        return preview["output"]

    return save_code_content(file_path, preview["code"], workspace_dir)


def save_generated_code_files(prompt, workspace_dir="workspace"):
    preview = build_generated_code_files_preview(prompt, workspace_dir)

    if not preview["ok"]:
        return preview["output"]

    return save_code_files_content(preview["files"], workspace_dir)


def save_generated_project_code_files(project_name, prompt, workspace_dir="workspace"):
    preview = build_project_code_files_preview(project_name, prompt, workspace_dir)

    if not preview["ok"]:
        return preview["output"]

    return save_code_files_content(preview["files"], workspace_dir)
