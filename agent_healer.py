import os

from agent_llm import invoke_llm
from agent_project_files import detect_broken_file, find_python_syntax_error
from agent_text import clean_code_output
from tools import (
    detect_missing_npm_package,
    detect_missing_python_package,
    extract_error_summary,
    get_fullstack_logs,
    install_npm_package,
    install_python_package,
    log_project_activity,
    preflight_fullstack_project,
    restart_fullstack_project,
    run_project_file,
)


WORKSPACE_DIR = "workspace"


def self_heal_project(project_name, entry_file, validate_flask_structure, patch_code):
    max_attempts = 5
    healed_files = []

    structure_fixes = validate_flask_structure(project_name)
    healed_files.extend(structure_fixes)

    for _ in range(max_attempts):
        syntax_file, syntax_error = find_python_syntax_error(project_name)

        if syntax_file:
            with open(syntax_file, "r", encoding="utf-8") as f:
                broken_code = f.read()

            fixed_code = patch_code(broken_code, syntax_error)

            with open(syntax_file, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            healed_files.append(syntax_file)
            continue

        result = run_project_file(project_name, entry_file)

        if result["returncode"] == 0:
            return f"""
PROJECT RUN SUCCESSFUL

HEALED FILES:
{chr(10).join(healed_files)}

OUTPUT:
{result["combined"]}
"""

        broken_file = detect_broken_file(result["combined"])

        if not broken_file:
            return f"""
AUTO HEAL FAILED

ERROR:
{result["combined"]}
"""

        with open(broken_file, "r", encoding="utf-8") as f:
            broken_code = f.read()

        error_summary = extract_error_summary(result["combined"])
        fixed_code = patch_code(broken_code, error_summary)

        with open(broken_file, "w", encoding="utf-8") as f:
            f.write(fixed_code)

        healed_files.append(broken_file)

    return f"""
AUTO HEAL FAILED AFTER {max_attempts} ATTEMPTS
"""


def detect_frontend_broken_file(frontend_logs, project_name):
    project_path = os.path.join(
        WORKSPACE_DIR,
        project_name,
        "frontend",
        "src",
    )

    possible_files = [
        "App.jsx",
        "api.js",
        "main.jsx",
        "style.css",
    ]

    for file_name in possible_files:
        if file_name in frontend_logs:
            return os.path.join(project_path, file_name)

    if "JSX" in frontend_logs or "Unexpected token" in frontend_logs:
        return os.path.join(project_path, "App.jsx")

    if "fetch" in frontend_logs or "API" in frontend_logs:
        return os.path.join(project_path, "api.js")

    return None


def patch_frontend_code(original_code, error_logs, file_name):
    prompt = f"""
You are a React/Vite debugging engine.

Fix this frontend file.

FILE NAME:
{file_name}

ERROR LOGS:
{error_logs}

CURRENT FILE CONTENT:
{original_code}

Rules:
- Return ONLY the corrected source code
- Do NOT return the file path
- Do NOT include FILE NAME
- Do NOT include markdown
- Do NOT include explanation
- Preserve React component structure
- The first line must be a valid import or JavaScript/JSX code
"""

    fixed = clean_code_output(invoke_llm(prompt))

    if fixed.strip().replace("\\", "/").endswith(file_name.replace("\\", "/")):
        return original_code

    if fixed.strip().startswith("workspace\\") or fixed.strip().startswith("workspace/"):
        return original_code

    return fixed


def heal_fullstack_project(project_name, patch_code):
    logs = get_fullstack_logs(project_name)

    backend_logs = logs.get("backend", "")
    frontend_logs = logs.get("frontend", "")

    healed_files = []
    installed_packages = []
    actions = []

    missing_python_package = detect_missing_python_package(backend_logs)

    if missing_python_package:
        install_output = install_python_package(
            missing_python_package,
            project_name,
        )

        installed_packages.append(f"Python: {missing_python_package}")
        actions.append(f"Installed Python package: {missing_python_package}")

        log_project_activity(
            project_name,
            "PYTHON_PACKAGE_INSTALLED",
            missing_python_package,
        )

        restart_fullstack_project(project_name)

        return f"""
FULLSTACK HEAL COMPLETE

ACTIONS:
{chr(10).join(actions)}

INSTALLED PACKAGES:
{chr(10).join(installed_packages)}

HEALED FILES:
None

INSTALL OUTPUT:
{install_output}
"""

    missing_npm_package = detect_missing_npm_package(frontend_logs)

    if missing_npm_package:
        install_output = install_npm_package(
            project_name,
            missing_npm_package,
        )

        installed_packages.append(f"NPM: {missing_npm_package}")
        actions.append(f"Installed NPM package: {missing_npm_package}")

        log_project_activity(
            project_name,
            "NPM_PACKAGE_INSTALLED",
            missing_npm_package,
        )

        restart_fullstack_project(project_name)

        return f"""
FULLSTACK HEAL COMPLETE

ACTIONS:
{chr(10).join(actions)}

INSTALLED PACKAGES:
{chr(10).join(installed_packages)}

HEALED FILES:
None

INSTALL OUTPUT:
{install_output}
"""

    if "Traceback" in backend_logs or "Error" in backend_logs or "Exception" in backend_logs:
        broken_file = detect_broken_file(backend_logs)

        if broken_file:
            try:
                with open(broken_file, "r", encoding="utf-8") as f:
                    broken_code = f.read()

                fixed_code = patch_code(
                    broken_code,
                    backend_logs,
                )

                with open(broken_file, "w", encoding="utf-8") as f:
                    f.write(fixed_code)

                healed_files.append(broken_file)
                actions.append(f"Healed backend file: {broken_file}")

                log_project_activity(
                    project_name,
                    "BACKEND_FILE_HEALED",
                    broken_file,
                )

                restart_fullstack_project(project_name)

                return f"""
FULLSTACK HEAL COMPLETE

ACTIONS:
{chr(10).join(actions)}

INSTALLED PACKAGES:
None

HEALED FILES:
{chr(10).join(healed_files)}
"""

            except Exception as e:
                return f"""
BACKEND HEAL FAILED

FILE:
{broken_file}

ERROR:
{e}
"""

    if (
        "Failed" in frontend_logs
        or "Error" in frontend_logs
        or "SyntaxError" in frontend_logs
        or "Unexpected token" in frontend_logs
    ):
        broken_frontend_file = detect_frontend_broken_file(
            frontend_logs,
            project_name,
        )

        if not broken_frontend_file:
            return f"""
FRONTEND ERROR DETECTED

Could not detect broken frontend file.

LOGS:
{frontend_logs}
"""

        try:
            with open(broken_frontend_file, "r", encoding="utf-8") as f:
                broken_code = f.read()

            fixed_code = patch_frontend_code(
                broken_code,
                frontend_logs,
                broken_frontend_file,
            )

            with open(broken_frontend_file, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            healed_files.append(broken_frontend_file)
            actions.append(f"Healed frontend file: {broken_frontend_file}")

            log_project_activity(
                project_name,
                "FRONTEND_FILE_HEALED",
                broken_frontend_file,
            )

            restart_fullstack_project(project_name)

            return f"""
FULLSTACK HEAL COMPLETE

ACTIONS:
{chr(10).join(actions)}

INSTALLED PACKAGES:
None

HEALED FILES:
{chr(10).join(healed_files)}
"""

        except Exception as e:
            return f"""
FRONTEND HEAL FAILED

FILE:
{broken_frontend_file}

ERROR:
{e}
"""

    return """
NO HEALING NEEDED

No backend or frontend errors found in logs.
"""


def heal_preflight_project(project_name, patch_code):
    preflight_result = preflight_fullstack_project(project_name)

    healed_files = []
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    python_files = [
        "backend/app.py",
        "backend/routes.py",
        "backend/database.py",
        "backend/models.py",
    ]

    for relative_file in python_files:
        file_name = os.path.basename(relative_file)

        if f"PYTHON ERROR: {file_name}" in preflight_result:
            file_path = os.path.join(project_path, relative_file)

            with open(file_path, "r", encoding="utf-8") as f:
                broken_code = f.read()

            if relative_file == "backend/database.py":
                fixed_code = """
import sqlite3

DATABASE_NAME = "app.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(\"\"\"
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT
        )
    \"\"\")

    connection.commit()
    connection.close()
"""
            else:
                fixed_code = patch_code(
                    broken_code,
                    preflight_result,
                )

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            healed_files.append(relative_file)

    if "package.json invalid JSON" in preflight_result or "package.json missing dev script" in preflight_result:
        package_path = os.path.join(
            project_path,
            "frontend",
            "package.json",
        )

        safe_package_json = {
            "name": "frontend",
            "private": True,
            "version": "0.0.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
            },
            "dependencies": {
                "react": "latest",
                "react-dom": "latest",
            },
            "devDependencies": {
                "@vitejs/plugin-react": "latest",
                "vite": "latest",
            },
        }

        with open(package_path, "w", encoding="utf-8") as f:
            import json

            json.dump(safe_package_json, f, indent=4)

        healed_files.append("frontend/package.json")

    second_preflight = preflight_fullstack_project(project_name)

    log_project_activity(
        project_name,
        "PREFLIGHT_HEAL_RUN",
        f"Healed files:\n{chr(10).join(healed_files) if healed_files else 'None'}",
    )

    return f"""
PREFLIGHT HEAL COMPLETE

PROJECT:
{project_name}

HEALED FILES:
{chr(10).join(healed_files) if healed_files else "None"}

====================
PREVIOUS PREFLIGHT
====================
{preflight_result}

====================
NEW PREFLIGHT
====================
{second_preflight}
"""
