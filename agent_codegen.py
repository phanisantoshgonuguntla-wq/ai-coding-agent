import difflib
import json
import os
import re
import uuid
from datetime import datetime

from agent_llm import invoke_llm
from agent_text import clean_code_output


CODEGEN_SESSIONS_DIR = os.path.join("_runtime", "codegen_sessions")
CODEGEN_CHECKPOINTS_DIR = os.path.join("_runtime", "codegen_checkpoints")
PYTHON_STDLIB_MODULES = {
    "collections",
    "csv",
    "datetime",
    "functools",
    "json",
    "math",
    "os",
    "pathlib",
    "random",
    "re",
    "sqlite3",
    "sys",
    "time",
    "typing",
    "urllib",
    "uuid",
}
PYTHON_LOCAL_MODULES = {
    "app",
    "database",
    "models",
    "routes",
}
JS_LOCAL_PREFIXES = (".", "/")
JS_BUILTIN_PACKAGES = {
    "react",
    "react-dom",
}


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


def generate_project_repair_files(prompt, project_context, validation_output):
    prompt = prompt.strip()
    validation_output = validation_output.strip()

    if not prompt:
        return "Please provide the original project-aware prompt."

    if not validation_output:
        return "Please provide validation output to repair."

    generation_prompt = f"""
You are a focused coding assistant repairing an existing generated project.

Project context:
{project_context}

Original user request:
{prompt}

Validation output:
{validation_output}

Generate the smallest safe repair needed to address the validation failure.

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
- Change only files needed for the repair
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


def _read_project_text(project_path, relative_path):
    file_path = os.path.join(project_path, relative_path)

    if not os.path.exists(file_path):
        return ""

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _normalize_dependency_name(name):
    return name.strip().lower().replace("_", "-")


def read_declared_python_dependencies(project_path):
    content = _read_project_text(project_path, "backend/requirements.txt")
    dependencies = set()

    for line in content.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        package = re.split(r"[<>=~!]", line, maxsplit=1)[0].strip()

        if package:
            dependencies.add(_normalize_dependency_name(package))

    return dependencies


def read_declared_js_dependencies(project_path):
    content = _read_project_text(project_path, "frontend/package.json")

    if not content:
        return set()

    try:
        package_json = json.loads(content)
    except Exception:
        return set()

    dependencies = set()

    for section in ["dependencies", "devDependencies"]:
        values = package_json.get(section, {})

        if isinstance(values, dict):
            dependencies.update(values.keys())

    return dependencies


def extract_python_imports(code):
    imports = set()

    for line in code.splitlines():
        stripped = line.strip()
        import_match = re.match(r"import\s+([A-Za-z_][A-Za-z0-9_\.]*)", stripped)
        from_match = re.match(r"from\s+([A-Za-z_][A-Za-z0-9_\.]*)\s+import\s+", stripped)

        module = None

        if import_match:
            module = import_match.group(1)
        elif from_match:
            module = from_match.group(1)

        if not module:
            continue

        imports.add(module.split(".")[0])

    return imports


def extract_js_imports(code):
    imports = set()
    patterns = [
        r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]",
        r"import\s+['\"]([^'\"]+)['\"]",
        r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, code):
            package = match.group(1)

            if package.startswith(JS_LOCAL_PREFIXES):
                continue

            if package.startswith("@"):
                parts = package.split("/")
                package = "/".join(parts[:2])
            else:
                package = package.split("/")[0]

            imports.add(package)

    return imports


def detect_dependency_warnings(project_path, entries):
    gaps = detect_dependency_gaps(project_path, entries)
    return [
        gap["message"]
        for gap in gaps
    ]


def detect_dependency_gaps(project_path, entries):
    declared_python = read_declared_python_dependencies(project_path)
    declared_js = read_declared_js_dependencies(project_path)
    gaps = []

    for entry in entries:
        path = (
            entry.get("project_relative_path")
            or entry.get("relative_path")
            or entry.get("path", "")
        )
        display_path = (entry.get("display_path") or path).replace("\\", "/")
        code = entry.get("code", "")

        if path.endswith(".py"):
            for module in sorted(extract_python_imports(code)):
                normalized = _normalize_dependency_name(module)

                if module in PYTHON_STDLIB_MODULES or module in PYTHON_LOCAL_MODULES:
                    continue

                if normalized not in declared_python:
                    gaps.append({
                        "kind": "python",
                        "name": normalized,
                        "source_file": display_path,
                        "dependency_file": "backend/requirements.txt",
                        "message": (
                            f"{display_path}: Python import '{module}' is not declared "
                            "in backend/requirements.txt"
                        ),
                    })

        if path.endswith((".js", ".jsx", ".ts", ".tsx")):
            for package in sorted(extract_js_imports(code)):
                if package in JS_BUILTIN_PACKAGES:
                    continue

                if package not in declared_js:
                    gaps.append({
                        "kind": "js",
                        "name": package,
                        "source_file": display_path,
                        "dependency_file": "frontend/package.json",
                        "message": (
                            f"{display_path}: JS package '{package}' is not declared "
                            "in frontend/package.json"
                        ),
                    })

    return gaps


def _preview_contains_path(entries, relative_path):
    normalized_path = relative_path.replace("\\", "/").lower()

    for entry in entries:
        candidate = (
            entry.get("project_relative_path")
            or entry.get("relative_path")
            or entry.get("path", "")
        ).replace("\\", "/").lower()

        if candidate == normalized_path:
            return True

    return False


def _build_requirements_patch(project_path, missing_packages):
    existing = _read_project_text(project_path, "backend/requirements.txt")
    lines = existing.splitlines()
    declared = read_declared_python_dependencies(project_path)

    for package in sorted(missing_packages):
        if _normalize_dependency_name(package) not in declared:
            lines.append(package)
            declared.add(_normalize_dependency_name(package))

    return "\n".join(lines).strip()


def _build_package_json_patch(project_path, missing_packages):
    existing = _read_project_text(project_path, "frontend/package.json")

    if existing:
        try:
            package_json = json.loads(existing)
        except Exception:
            return ""
    else:
        package_json = {
            "name": "generated-app",
            "private": True,
            "version": "0.0.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
            },
            "dependencies": {},
            "devDependencies": {},
        }

    dependencies = package_json.setdefault("dependencies", {})

    if not isinstance(dependencies, dict):
        dependencies = {}
        package_json["dependencies"] = dependencies

    for package in sorted(missing_packages):
        dependencies.setdefault(package, "latest")

    return json.dumps(package_json, indent=2)


def build_dependency_patch_entries(project_path, entries):
    gaps = detect_dependency_gaps(project_path, entries)
    python_packages = {
        gap["name"]
        for gap in gaps
        if gap["kind"] == "python"
    }
    js_packages = {
        gap["name"]
        for gap in gaps
        if gap["kind"] == "js"
    }
    patches = []

    if python_packages and not _preview_contains_path(entries, "backend/requirements.txt"):
        code = _build_requirements_patch(project_path, python_packages)

        if code:
            patches.append({
                "path": "backend/requirements.txt",
                "code": code,
                "dependency_patch": True,
            })

    if js_packages and not _preview_contains_path(entries, "frontend/package.json"):
        code = _build_package_json_patch(project_path, js_packages)

        if code:
            patches.append({
                "path": "frontend/package.json",
                "code": code,
                "dependency_patch": True,
            })

    return patches


PROJECT_CONTEXT_FILE_CATEGORIES = {
    "metadata": [
        "project_spec.json",
        "project_config.json",
    ],
    "backend": [
        "backend/app.py",
        "backend/routes.py",
        "backend/Program.cs",
        "backend/index.php",
    ],
    "database": [
        "backend/models.py",
        "backend/database.py",
        "backend/database.php",
    ],
    "frontend": [
        "frontend/package.json",
        "frontend/src/App.jsx",
        "frontend/src/api.js",
        "frontend/src/style.css",
    ],
    "dependencies": [
        "backend/requirements.txt",
        "backend/GeneratedApp.Api.csproj",
        "frontend/package.json",
    ],
}


PROJECT_CONTEXT_KEYWORDS = {
    "backend": [
        "api",
        "backend",
        "endpoint",
        "route",
        "flask",
        "controller",
        "server",
        "request",
        "response",
    ],
    "database": [
        "database",
        "sqlite",
        "schema",
        "table",
        "model",
        "field",
        "column",
        "persist",
        "storage",
    ],
    "frontend": [
        "frontend",
        "react",
        "ui",
        "button",
        "form",
        "page",
        "component",
        "style",
        "css",
        "screen",
        "display",
    ],
    "dependencies": [
        "dependency",
        "dependencies",
        "package",
        "install",
        "requirements",
        "npm",
        "library",
        "import",
    ],
}


def select_project_context_files(prompt):
    prompt_lower = prompt.lower()
    selected_categories = ["metadata"]

    for category, keywords in PROJECT_CONTEXT_KEYWORDS.items():
        if any(keyword in prompt_lower for keyword in keywords):
            selected_categories.append(category)

    if selected_categories == ["metadata"]:
        selected_categories.extend(["backend", "frontend"])

    selected_files = []

    for category in selected_categories:
        for file_path in PROJECT_CONTEXT_FILE_CATEGORIES[category]:
            if file_path not in selected_files:
                selected_files.append(file_path)

    return selected_files


def build_project_context(project_name, prompt="", workspace_dir="workspace"):
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
    context_files = select_project_context_files(prompt)
    existing_context_files = [
        relative_path
        for relative_path in context_files
        if os.path.exists(os.path.join(project_path, relative_path))
    ]
    file_context = "".join(
        _read_context_file(project_path, relative_path)
        for relative_path in existing_context_files
    ).strip()
    spec_summary = json.dumps(spec, indent=2) if spec else "{}"

    return {
        "ok": True,
        "project_name": project_name,
        "project_path": project_path,
        "stack_key": stack_key,
        "stack_label": stack_label,
        "context_files": existing_context_files,
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


def explain_project_context(project_name, prompt, workspace_dir="workspace"):
    context = build_project_context(project_name, prompt, workspace_dir)

    if not context["ok"]:
        return context["output"]

    return f"""PROJECT CONTEXT

PROJECT:
{context["project_name"]}

STACK:
{context["stack_label"]}

INCLUDED FILES:
{chr(10).join(context["context_files"]) if context["context_files"] else "None"}
"""


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


def _format_dependency_warning_section(dependency_warnings):
    if not dependency_warnings:
        return [
            "DEPENDENCY WARNINGS:",
            "None",
            "",
            "====================",
            "",
        ]

    return [
        "DEPENDENCY WARNINGS:",
        *dependency_warnings,
        "",
        "====================",
        "",
    ]


def _format_project_multi_file_preview(entries, context_files, dependency_warnings=None):
    context_section = [
        "PROJECT CONTEXT FILES:",
        *(context_files or ["None"]),
        "",
        "====================",
        "",
    ]
    dependency_section = _format_dependency_warning_section(dependency_warnings or [])
    return (
        "\n".join(context_section)
        + "\n".join(dependency_section)
        + _format_multi_file_preview(entries)
    )


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
            "dependency_patch": file.get("dependency_patch", False),
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

    context = build_project_context(project_name, prompt, workspace_dir)

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
    files = files + build_dependency_patch_entries(project_workspace, files)
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

    dependency_warnings = detect_dependency_warnings(
        project_workspace,
        preview["files"],
    )

    return {
        "ok": True,
        "project_name": context["project_name"],
        "context_files": context["context_files"],
        "dependency_warnings": dependency_warnings,
        "files": preview["files"],
        "has_existing_files": preview["has_existing_files"],
        "output": _format_project_multi_file_preview(
            preview["files"],
            context["context_files"],
            dependency_warnings,
        ),
    }


def _build_project_preview_from_generated_output(project_name, prompt, generated_output, workspace_dir):
    context = build_project_context(project_name, prompt, workspace_dir)

    if not context["ok"]:
        return context

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
    files = files + build_dependency_patch_entries(project_workspace, files)
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

    dependency_warnings = detect_dependency_warnings(
        project_workspace,
        preview["files"],
    )

    return {
        "ok": True,
        "project_name": context["project_name"],
        "context_files": context["context_files"],
        "dependency_warnings": dependency_warnings,
        "files": preview["files"],
        "has_existing_files": preview["has_existing_files"],
        "output": _format_project_multi_file_preview(
            preview["files"],
            context["context_files"],
            dependency_warnings,
        ),
    }


def build_project_repair_files_preview(project_name, prompt, validation_output, workspace_dir="workspace"):
    prompt = prompt.strip()
    validation_output = validation_output.strip()

    if not prompt:
        return {
            "ok": False,
            "error": "Please provide the original project-aware prompt.",
            "output": "Please provide the original project-aware prompt.",
        }

    if not validation_output:
        return {
            "ok": False,
            "error": "Please provide validation output to repair.",
            "output": "Please provide validation output to repair.",
        }

    context = build_project_context(project_name, prompt, workspace_dir)

    if not context["ok"]:
        return context

    generated_output = generate_project_repair_files(
        prompt,
        context["context"],
        validation_output,
    )

    preview = _build_project_preview_from_generated_output(
        project_name,
        prompt,
        generated_output,
        workspace_dir,
    )

    if not preview["ok"]:
        return preview

    preview["output"] = (
        "PROJECT REPAIR PREVIEW\n\n"
        + preview["output"]
    )
    return preview


def preview_generated_code(file_path, prompt, workspace_dir="workspace"):
    return build_generated_code_preview(file_path, prompt, workspace_dir)["output"]


def preview_generated_code_files(prompt, workspace_dir="workspace"):
    return build_generated_code_files_preview(prompt, workspace_dir)["output"]


def preview_project_code_files(project_name, prompt, workspace_dir="workspace"):
    return build_project_code_files_preview(project_name, prompt, workspace_dir)["output"]


def preview_project_repair_files(project_name, prompt, validation_output, workspace_dir="workspace"):
    return build_project_repair_files_preview(
        project_name,
        prompt,
        validation_output,
        workspace_dir,
    )["output"]


def _get_codegen_checkpoints_dir(workspace_dir):
    return os.path.join(workspace_dir, CODEGEN_CHECKPOINTS_DIR)


def _build_checkpoint_id():
    return (
        "checkpoint_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid.uuid4().hex[:8]
    )


def _normalize_save_entries(files, workspace_dir):
    entries = []

    if not files:
        raise ValueError("Please preview generated code files before saving.")

    for file in files:
        code = file.get("code", "")

        if not code.strip():
            raise ValueError("Generated file content cannot be empty.")

        file_path = file.get("relative_path") or file.get("path") or ""

        try:
            relative_path, target_path = _normalize_workspace_path(
                file_path,
                workspace_dir,
            )
        except ValueError as error:
            raise ValueError(str(error)) from error

        entries.append({
            "relative_path": relative_path,
            "display_path": relative_path.replace("\\", "/"),
            "target_path": target_path,
            "code": code,
        })

    return entries


def _create_codegen_checkpoint(entries, workspace_dir, reason):
    checkpoints_dir = _get_codegen_checkpoints_dir(workspace_dir)
    os.makedirs(checkpoints_dir, exist_ok=True)

    checkpoint_id = _build_checkpoint_id()
    timestamp = datetime.now().isoformat(timespec="seconds")
    checkpoint_files = []

    for entry in entries:
        target_path = entry["target_path"]
        existed = os.path.exists(target_path)
        content = ""

        if existed:
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError as error:
                raise ValueError(
                    "Could not create checkpoint because an existing file is not UTF-8 text: "
                    f"workspace/{entry['display_path']}"
                ) from error

        checkpoint_files.append({
            "relative_path": entry["relative_path"],
            "display_path": entry["display_path"],
            "existed": existed,
            "content": content,
        })

    checkpoint = {
        "id": checkpoint_id,
        "reason": reason,
        "created_at": timestamp,
        "files": checkpoint_files,
    }
    checkpoint_path = os.path.join(checkpoints_dir, f"{checkpoint_id}.json")

    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)

    return checkpoint


def _write_save_entries(entries):
    saved_paths = []

    for entry in entries:
        os.makedirs(os.path.dirname(entry["target_path"]), exist_ok=True)

        with open(entry["target_path"], "w", encoding="utf-8") as f:
            f.write(entry["code"])
            f.write("\n")

        saved_paths.append(f"workspace/{entry['display_path']}")

    return saved_paths


def save_code_content(file_path, code, workspace_dir="workspace"):
    if not code.strip():
        return "Please preview generated code before saving."

    try:
        entries = _normalize_save_entries(
            [{"relative_path": file_path, "code": code}],
            workspace_dir,
        )
        checkpoint = _create_codegen_checkpoint(entries, workspace_dir, "single_file_save")
    except ValueError as error:
        return str(error)

    saved_paths = _write_save_entries(entries)
    display_path = saved_paths[0]

    return f"""CODE GENERATED AND SAVED

CHECKPOINT:
{checkpoint["id"]}

FILE:
{display_path}

CODE:
{code}
"""


def save_code_files_content(files, workspace_dir="workspace"):
    if not files:
        return "Please preview generated code files before saving."

    try:
        entries = _normalize_save_entries(files, workspace_dir)
        checkpoint = _create_codegen_checkpoint(entries, workspace_dir, "multi_file_save")
    except ValueError as error:
        return str(error)

    saved_paths = _write_save_entries(entries)

    return f"""CODE FILES SAVED

CHECKPOINT:
{checkpoint["id"]}

FILES:
{chr(10).join(saved_paths)}
"""


def _get_codegen_sessions_dir(workspace_dir):
    return os.path.join(workspace_dir, CODEGEN_SESSIONS_DIR)


def _read_json_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _validation_status(validation_output):
    if not validation_output:
        return "not_run"

    if any(marker in validation_output for marker in ["FAIL:", "NEEDS ATTENTION", "NEEDS FIX"]):
        return "failed"

    return "passed"


def record_codegen_session(
    session_type,
    project_name,
    prompt,
    files,
    validation_output="",
    dependency_warnings=None,
    workspace_dir="workspace",
):
    sessions_dir = _get_codegen_sessions_dir(workspace_dir)
    os.makedirs(sessions_dir, exist_ok=True)

    timestamp = datetime.now().isoformat(timespec="seconds")
    session_id = (
        "codegen_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid.uuid4().hex[:8]
    )
    file_paths = [
        file.get("display_path")
        or file.get("relative_path", "").replace("\\", "/")
        for file in files
    ]
    session = {
        "id": session_id,
        "type": session_type,
        "project_name": project_name,
        "prompt": prompt,
        "files": file_paths,
        "dependency_warnings": dependency_warnings or [],
        "validation_status": _validation_status(validation_output),
        "validation_output": validation_output,
        "created_at": timestamp,
    }
    session_path = os.path.join(sessions_dir, f"{session_id}.json")

    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)

    return session


def _read_codegen_session_file(session_path):
    return _read_json_file(session_path)


def list_codegen_sessions(workspace_dir="workspace", limit=20):
    sessions_dir = _get_codegen_sessions_dir(workspace_dir)

    if not os.path.exists(sessions_dir):
        return "No codegen sessions found."

    sessions = []

    for file_name in os.listdir(sessions_dir):
        if not file_name.endswith(".json"):
            continue

        session = _read_codegen_session_file(os.path.join(sessions_dir, file_name))

        if session:
            sessions.append(session)

    if not sessions:
        return "No codegen sessions found."

    sessions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    lines = [
        "CODEGEN SESSIONS",
        "",
    ]

    for session in sessions[:limit]:
        lines.append(
            f"{session.get('id')} | {session.get('project_name')} | "
            f"{session.get('type')} | {session.get('validation_status')} | "
            f"{session.get('created_at')}"
        )

    return "\n".join(lines)


def show_codegen_session(session_id, workspace_dir="workspace"):
    session_id = session_id.strip()

    if not session_id:
        return "Use format: show codegen session <session_id>"

    sessions_dir = _get_codegen_sessions_dir(workspace_dir)
    session_path = os.path.join(sessions_dir, f"{session_id}.json")

    if not os.path.exists(session_path):
        return f"Codegen session not found: {session_id}"

    session = _read_codegen_session_file(session_path)

    if not session:
        return f"Could not read codegen session: {session_id}"

    return f"""CODEGEN SESSION

ID:
{session.get("id")}

TYPE:
{session.get("type")}

PROJECT:
{session.get("project_name")}

CREATED:
{session.get("created_at")}

VALIDATION:
{session.get("validation_status")}

DEPENDENCY WARNINGS:
{chr(10).join(session.get("dependency_warnings", [])) or "None"}

FILES:
{chr(10).join(session.get("files", [])) or "None"}

PROMPT:
{session.get("prompt", "")}

VALIDATION OUTPUT:
{session.get("validation_output", "") or "Not run"}
"""


def _read_codegen_checkpoint(checkpoint_id, workspace_dir):
    checkpoint_id = checkpoint_id.strip()

    if not checkpoint_id:
        return None

    checkpoints_dir = _get_codegen_checkpoints_dir(workspace_dir)
    checkpoint_path = os.path.join(checkpoints_dir, f"{checkpoint_id}.json")

    if not os.path.exists(checkpoint_path):
        return None

    return _read_json_file(checkpoint_path)


def list_codegen_checkpoints(workspace_dir="workspace", limit=20):
    checkpoints_dir = _get_codegen_checkpoints_dir(workspace_dir)

    if not os.path.exists(checkpoints_dir):
        return "No codegen checkpoints found."

    checkpoints = []

    for file_name in os.listdir(checkpoints_dir):
        if not file_name.endswith(".json"):
            continue

        checkpoint = _read_json_file(os.path.join(checkpoints_dir, file_name))

        if checkpoint:
            checkpoints.append(checkpoint)

    if not checkpoints:
        return "No codegen checkpoints found."

    checkpoints.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    lines = [
        "CODEGEN CHECKPOINTS",
        "",
    ]

    for checkpoint in checkpoints[:limit]:
        files = checkpoint.get("files", [])
        lines.append(
            f"{checkpoint.get('id')} | {checkpoint.get('reason')} | "
            f"{len(files)} files | {checkpoint.get('created_at')}"
        )

    return "\n".join(lines)


def show_codegen_checkpoint(checkpoint_id, workspace_dir="workspace"):
    checkpoint_id = checkpoint_id.strip()

    if not checkpoint_id:
        return "Use format: show codegen checkpoint <checkpoint_id>"

    checkpoint = _read_codegen_checkpoint(checkpoint_id, workspace_dir)

    if not checkpoint:
        return f"Codegen checkpoint not found: {checkpoint_id}"

    file_lines = []

    for file in checkpoint.get("files", []):
        status = "restore" if file.get("existed") else "delete on restore"
        file_lines.append(f"{file.get('display_path')} ({status})")

    return f"""CODEGEN CHECKPOINT

ID:
{checkpoint.get("id")}

REASON:
{checkpoint.get("reason")}

CREATED:
{checkpoint.get("created_at")}

FILES:
{chr(10).join(file_lines) or "None"}
"""


def restore_codegen_checkpoint(checkpoint_id, workspace_dir="workspace"):
    checkpoint_id = checkpoint_id.strip()

    if not checkpoint_id:
        return "Use format: restore codegen checkpoint <checkpoint_id>"

    checkpoint = _read_codegen_checkpoint(checkpoint_id, workspace_dir)

    if not checkpoint:
        return f"Codegen checkpoint not found: {checkpoint_id}"

    current_entries = []

    for file in checkpoint.get("files", []):
        try:
            relative_path, target_path = _normalize_workspace_path(
                file.get("relative_path", ""),
                workspace_dir,
            )
        except ValueError as error:
            return str(error)

        current_entries.append({
            "relative_path": relative_path,
            "display_path": relative_path.replace("\\", "/"),
            "target_path": target_path,
            "code": file.get("content", ""),
        })

    try:
        pre_restore = _create_codegen_checkpoint(
            current_entries,
            workspace_dir,
            f"before_restore_{checkpoint_id}",
        )
    except ValueError as error:
        return str(error)

    restored_lines = []

    for file in checkpoint.get("files", []):
        relative_path, target_path = _normalize_workspace_path(
            file.get("relative_path", ""),
            workspace_dir,
        )
        display_path = relative_path.replace("\\", "/")

        if file.get("existed"):
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(file.get("content", ""))

            restored_lines.append(f"workspace/{display_path} (restored)")
        else:
            if os.path.exists(target_path):
                os.remove(target_path)

            restored_lines.append(f"workspace/{display_path} (deleted)")

    return f"""CODEGEN CHECKPOINT RESTORED

ID:
{checkpoint_id}

PRE-RESTORE CHECKPOINT:
{pre_restore["id"]}

FILES:
{chr(10).join(restored_lines)}
"""


def _project_relative_path_from_file(file, project_name):
    raw_path = (
        file.get("project_relative_path")
        or file.get("relative_path")
        or file.get("display_path")
        or file.get("path")
        or ""
    )
    normalized_path = raw_path.replace("\\", "/")

    if normalized_path.startswith("workspace/"):
        normalized_path = normalized_path[len("workspace/"):]

    project_prefix = f"{project_name}/"

    if normalized_path.startswith(project_prefix):
        normalized_path = normalized_path[len(project_prefix):]

    return normalized_path


def build_codegen_validation_plan(project_name, files, stack_key="react_flask_sqlite"):
    changed_paths = [
        _project_relative_path_from_file(file, project_name)
        for file in files
    ]
    changed_paths = [
        path
        for path in changed_paths
        if path
    ]
    changed_set = set(changed_paths)
    touches_backend = any(path.startswith("backend/") for path in changed_set)
    touches_frontend = any(path.startswith("frontend/") for path in changed_set)
    touches_database = any(
        path in {
            "backend/database.py",
            "backend/models.py",
            "backend/database.php",
            "backend/Program.cs",
        }
        for path in changed_set
    )
    touches_api_contract = any(
        path in {
            "backend/routes.py",
            "backend/app.py",
            "backend/index.php",
            "backend/Program.cs",
            "frontend/src/api.js",
        }
        for path in changed_set
    )
    touches_frontend_build = touches_frontend or "frontend/package.json" in changed_set
    touches_python_backend = any(
        path.startswith("backend/") and path.endswith(".py")
        for path in changed_set
    ) or "backend/requirements.txt" in changed_set
    checks = []

    if stack_key == "react_flask_sqlite":
        if touches_python_backend:
            checks.append({
                "key": "backend_imports",
                "label": "Backend import validation",
                "reason": "Python backend files changed.",
            })

        if touches_database:
            checks.append({
                "key": "database_schema",
                "label": "Database schema validation",
                "reason": "Database/model files changed.",
            })
            checks.append({
                "key": "sqlite_runtime",
                "label": "SQLite runtime validation",
                "reason": "Database/model files changed.",
            })

        if touches_api_contract or (touches_backend and touches_frontend):
            checks.append({
                "key": "api_contract",
                "label": "API contract validation",
                "reason": "API-facing backend or frontend files changed.",
            })

        if touches_frontend_build:
            checks.append({
                "key": "frontend_build",
                "label": "Frontend production build",
                "reason": "Frontend files changed.",
            })

        if touches_backend and touches_frontend:
            checks.append({
                "key": "full_app_validation",
                "label": "Full app validation",
                "reason": "Backend and frontend changed together.",
            })
    else:
        if touches_frontend_build:
            checks.append({
                "key": "frontend_build",
                "label": "Frontend production build",
                "reason": "Frontend files changed.",
            })

        if touches_backend:
            checks.append({
                "key": "full_app_validation",
                "label": "Full app validation",
                "reason": "Stack-specific backend validation is broad for this stack.",
            })

    if not checks:
        checks.append({
            "key": "full_app_validation",
            "label": "Full app validation",
            "reason": "Changed files did not match a narrower validator.",
        })

    deduped_checks = []
    seen = set()

    for check in checks:
        if check["key"] in seen:
            continue

        deduped_checks.append(check)
        seen.add(check["key"])

    return {
        "changed_paths": changed_paths,
        "checks": deduped_checks,
    }


def _validation_result_failed(output):
    return any(
        marker in output
        for marker in ["FAIL:", "NEEDS ATTENTION", "NEEDS FIX", "failed", "not found"]
    )


def validate_codegen_changes(project_name, files, stack_key, validators):
    if not files:
        return "Please provide changed files to validate."

    plan = build_codegen_validation_plan(project_name, files, stack_key)
    results = []
    failures = []

    for check in plan["checks"]:
        validator = validators.get(check["key"])

        if not validator:
            output = f"SKIP: Validator not configured for {check['key']}."
        else:
            try:
                output = validator(project_name)
            except Exception as error:
                output = f"FAIL: {check['label']} raised an error: {error}"

        section = f"""CHECK:
{check["label"]}

REASON:
{check["reason"]}

RESULT:
{output}"""
        results.append(section)

        if _validation_result_failed(output):
            failures.append(check["label"])

    final_status = "READY" if not failures else "NEEDS ATTENTION"

    return f"""CODEGEN TARGETED VALIDATION REPORT

PROJECT:
{project_name}

STACK:
{stack_key}

FINAL STATUS:
{final_status}

CHANGED FILES:
{chr(10).join(plan["changed_paths"]) or "None"}

VALIDATION PLAN:
{chr(10).join("- " + check["label"] for check in plan["checks"])}

RESULTS:
{chr(10).join(results)}
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
