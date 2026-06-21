import difflib
import os

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


def preview_generated_code(file_path, prompt, workspace_dir="workspace"):
    return build_generated_code_preview(file_path, prompt, workspace_dir)["output"]


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


def save_generated_code(file_path, prompt, workspace_dir="workspace"):
    preview = build_generated_code_preview(file_path, prompt, workspace_dir)

    if not preview["ok"]:
        return preview["output"]

    return save_code_content(file_path, preview["code"], workspace_dir)
