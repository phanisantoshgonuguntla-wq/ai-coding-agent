import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

import agent_healer
from agent_project_files import detect_broken_file
from agent_stacks import get_project_stack_key
from tools import (
    ensure_project_config,
    log_project_activity,
    preflight_fullstack_project,
    run_fullstack_project,
)


WORKSPACE_DIR = "workspace"


def validate_api_contract(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    api_file = os.path.join(project_path, "frontend", "src", "api.js")
    routes_file = os.path.join(project_path, "backend", "routes.py")

    if not os.path.exists(api_file):
        return "frontend/src/api.js not found."

    if not os.path.exists(routes_file):
        return "backend/routes.py not found."

    with open(api_file, "r", encoding="utf-8") as f:
        api_code = f.read()

    with open(routes_file, "r", encoding="utf-8") as f:
        routes_code = f.read()

    project_config = ensure_project_config(project_name, "react_flask_sqlite")
    backend_url_pattern = re.escape(project_config["backend_url"])

    frontend_routes = re.findall(
        rf"{backend_url_pattern}([^\"']+)",
        api_code,
    )

    backend_routes = re.findall(
        r'@app\.route\s*\(\s*["\']([^"\']+)["\']',
        routes_code,
    )

    backend_routes += re.findall(
        r'@app\.(get|post|put|delete)\s*\(\s*["\']([^"\']+)["\']',
        routes_code,
    )

    backend_routes = [
        route if isinstance(route, str) else route[1]
        for route in backend_routes
    ]

    frontend_routes = sorted(set(frontend_routes))
    backend_routes = sorted(set(backend_routes))

    missing_in_backend = [
        route for route in frontend_routes
        if route not in backend_routes
    ]

    unused_backend = [
        route for route in backend_routes
        if route not in frontend_routes
    ]

    results = []
    results.append("FRONTEND CALLS:")
    results.extend(frontend_routes if frontend_routes else ["None"])
    results.append("")
    results.append("BACKEND ROUTES:")
    results.extend(backend_routes if backend_routes else ["None"])
    results.append("")
    results.append("CONTRACT CHECK:")

    if missing_in_backend:
        for route in missing_in_backend:
            results.append(f"FAIL: Frontend calls {route}, but backend route is missing.")
    else:
        results.append("PASS: All frontend routes exist in backend.")

    if unused_backend:
        for route in unused_backend:
            results.append(f"WARN: Backend route {route} is not used by frontend.")

    log_project_activity(
        project_name,
        "API_CONTRACT_VALIDATED",
        "\n".join(results),
    )

    return f"""
API CONTRACT REPORT

PROJECT:
{project_name}

{chr(10).join(results)}
"""


def fix_api_contract(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    routes_file = os.path.join(project_path, "backend", "routes.py")
    api_file = os.path.join(project_path, "frontend", "src", "api.js")

    fixed_routes_code = """
from flask import request, jsonify
from models import get_items, add_item


def register_routes(app):

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response

    @app.route("/api/items", methods=["GET"])
    def list_items():
        return jsonify(get_items())

    @app.route("/api/items", methods=["POST", "OPTIONS"])
    def create_item():
        if request.method == "OPTIONS":
            return jsonify({}), 200

        data = request.get_json() or {}
        title = data.get("title")
        description = data.get("description", "")
        email = data.get("email", "")
        phone = data.get("phone", "")

        if not title:
            return jsonify({"error": "title is required"}), 400

        add_item(title, description, email, phone)
        return jsonify({"message": "item added"}), 201
"""

    project_config = ensure_project_config(project_name, "react_flask_sqlite")

    fixed_api_code = """
const API_URL = "__BACKEND_URL__/api/items";

export async function getItems() {
    const response = await fetch(API_URL);
    return response.json();
}

export async function addItem(item) {
    const response = await fetch(API_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(item)
    });

    return response.json();
}
""".replace("__BACKEND_URL__", project_config["backend_url"])

    with open(routes_file, "w", encoding="utf-8") as f:
        f.write(fixed_routes_code)

    if os.path.exists(api_file):
        with open(api_file, "w", encoding="utf-8") as f:
            f.write(fixed_api_code)

    validation_result = validate_api_contract(project_name)

    log_project_activity(
        project_name,
        "API_CONTRACT_FIXED",
        "Replaced routes.py and api.js with safe /api/items contract.",
    )

    return f"""
CONTRACT FIX COMPLETE

PROJECT:
{project_name}

FIXED FILES:
backend/routes.py
frontend/src/api.js

====================
NEW VALIDATION
====================
{validation_result}
"""


def validate_database_schema(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    database_file = os.path.join(project_path, "backend", "database.py")
    models_file = os.path.join(project_path, "backend", "models.py")

    if not os.path.exists(database_file):
        return "backend/database.py not found."

    if not os.path.exists(models_file):
        return "backend/models.py not found."

    with open(database_file, "r", encoding="utf-8") as f:
        database_code = f.read()

    with open(models_file, "r", encoding="utf-8") as f:
        models_code = f.read()

    issues = []

    if "CREATE TABLE IF NOT EXISTS items" not in database_code:
        issues.append("FAIL: Missing items table in database.py")
    else:
        issues.append("PASS: items table exists")

    required_columns = ["id", "title", "description"]
    table_match = re.search(
        r"CREATE TABLE IF NOT EXISTS items\s*\((.*?)\)",
        database_code,
        re.DOTALL,
    )

    table_definition = ""

    if table_match:
        table_definition = table_match.group(1)

    for column in required_columns:
        if column not in table_definition:
            issues.append(f"FAIL: Missing column in database.py: {column}")
        else:
            issues.append(f"PASS: Column found in database.py: {column}")

    model_requirements = [
        "get_items",
        "add_item",
        "SELECT",
        "INSERT INTO items",
    ]

    for requirement in model_requirements:
        if requirement not in models_code:
            issues.append(f"FAIL: Missing in models.py: {requirement}")
        else:
            issues.append(f"PASS: Found in models.py: {requirement}")

    log_project_activity(
        project_name,
        "DATABASE_SCHEMA_VALIDATED",
        "\n".join(issues),
    )

    return f"""
DATABASE SCHEMA REPORT

PROJECT:
{project_name}

RESULTS:
{chr(10).join(issues)}
"""


def fix_database_schema(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    database_file = os.path.join(project_path, "backend", "database.py")
    models_file = os.path.join(project_path, "backend", "models.py")

    safe_database_code = """
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
            description TEXT,
            email TEXT,
            phone TEXT
        )
    \"\"\")

    connection.commit()
    connection.close()
"""

    safe_models_code = """
from database import get_connection


def get_items():
    connection = get_connection()
    items = connection.execute(
        "SELECT id, title, description, email, phone FROM items ORDER BY id DESC"
    ).fetchall()
    connection.close()
    return [dict(item) for item in items]


def add_item(title, description="", email="", phone=""):
    connection = get_connection()
    connection.execute(
        "INSERT INTO items (title, description, email, phone) VALUES (?, ?, ?, ?)",
        (title, description, email, phone)
    )
    connection.commit()
    connection.close()
"""

    os.makedirs(os.path.dirname(database_file), exist_ok=True)

    with open(database_file, "w", encoding="utf-8") as f:
        f.write(safe_database_code)

    with open(models_file, "w", encoding="utf-8") as f:
        f.write(safe_models_code)

    validation_result = validate_database_schema(project_name)

    log_project_activity(
        project_name,
        "DATABASE_SCHEMA_FIXED",
        "Replaced database.py and models.py with safe items schema.",
    )

    return f"""
DATABASE SCHEMA FIX COMPLETE

PROJECT:
{project_name}

FIXED FILES:
backend/database.py
backend/models.py

====================
NEW VALIDATION
====================
{validation_result}
"""


def wait_for_backend(base_url, retries=10, delay=1):
    for _ in range(retries):
        try:
            with urllib.request.urlopen(f"{base_url}/api/items", timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(delay)

    return False


def test_runtime_endpoints(project_name):
    project_config = ensure_project_config(
        project_name,
        get_project_stack_key(project_name),
    )
    base_url = project_config["backend_url"]
    results = []

    if not wait_for_backend(base_url):
        results.append("FAIL: Backend did not start after waiting.")
        return f"""
RUNTIME ENDPOINT TEST

PROJECT:
{project_name}

RESULTS:
{chr(10).join(results)}
"""

    try:
        with urllib.request.urlopen(f"{base_url}/api/items", timeout=5) as response:
            body = response.read().decode("utf-8")
            status = response.status

        if status == 200:
            results.append("PASS: GET /api/items passed")
        else:
            results.append(f"FAIL: GET /api/items failed with status {status}")
    except Exception as e:
        results.append(f"FAIL: GET /api/items failed: {e}")

    try:
        data = json.dumps({
            "title": "Runtime test item",
            "description": "Created by endpoint tester",
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{base_url}/api/items",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            status = response.status

        if status in [200, 201]:
            results.append("PASS: POST /api/items passed")
        else:
            results.append(f"FAIL: POST /api/items failed with status {status}")
    except Exception as e:
        results.append(f"FAIL: POST /api/items failed: {e}")

    try:
        with urllib.request.urlopen(f"{base_url}/api/items", timeout=5) as response:
            body = response.read().decode("utf-8")

        if "Runtime test item" in body:
            results.append("PASS: Database insert verified")
        else:
            results.append("WARN: POST succeeded, but inserted item was not found in GET response")
    except Exception as e:
        results.append(f"FAIL: Insert verification failed: {e}")

    log_project_activity(
        project_name,
        "RUNTIME_ENDPOINT_TEST",
        "\n".join(results),
    )

    return f"""
RUNTIME ENDPOINT TEST

PROJECT:
{project_name}

RESULTS:
{chr(10).join(results)}
"""


def validate_backend_imports(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    app_file = os.path.join(project_path, "backend", "app.py")

    if not os.path.exists(app_file):
        return "backend/app.py not found."

    with open(app_file, "r", encoding="utf-8") as f:
        app_code = f.read()

    issues = []

    bad_imports = [
        "from backend.routes",
        "from backend.database",
        "from backend.models",
        "import backend.routes",
        "import backend.database",
        "import backend.models",
    ]

    for bad_import in bad_imports:
        if bad_import in app_code:
            issues.append(f"FAIL: Bad backend import found: {bad_import}")

    required_checks = [
        "from flask import Flask",
        "from routes import register_routes",
        "from database import init_db",
        "app = Flask(__name__)",
        "init_db()",
        "register_routes(app)",
    ]

    for check in required_checks:
        if check in app_code:
            issues.append(f"PASS: Found: {check}")
        else:
            issues.append(f"FAIL: Missing: {check}")

    if not any(issue.startswith("FAIL") for issue in issues):
        issues.append("PASS: Backend imports look valid.")

    log_project_activity(
        project_name,
        "BACKEND_IMPORTS_VALIDATED",
        "\n".join(issues),
    )

    return f"""
BACKEND IMPORT VALIDATION

PROJECT:
{project_name}

RESULTS:
{chr(10).join(issues)}
"""


def fix_backend_imports(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    app_file = os.path.join(project_path, "backend", "app.py")

    if not os.path.exists(app_file):
        return "backend/app.py not found."

    fixed_app_code = """
from flask import Flask
from routes import register_routes
from database import init_db

app = Flask(__name__)

init_db()
register_routes(app)

if __name__ == "__main__":
    app.run(debug=True)
"""

    with open(app_file, "w", encoding="utf-8") as f:
        f.write(fixed_app_code)

    validation_result = validate_backend_imports(project_name)

    log_project_activity(
        project_name,
        "BACKEND_IMPORTS_FIXED",
        "Replaced backend/app.py with safe local imports.",
    )

    return f"""
BACKEND IMPORT FIX COMPLETE

PROJECT:
{project_name}

FIXED FILE:
backend/app.py

====================
NEW VALIDATION
====================
{validation_result}
"""


def smoke_test_backend(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    backend_path = os.path.join(project_path, "backend")

    try:
        process = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=backend_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout, stderr = process.communicate(timeout=5)
            combined = (stdout or "") + "\n" + (stderr or "")

            if process.returncode == 0:
                return {
                    "ok": True,
                    "log": combined,
                }

            return {
                "ok": False,
                "log": combined,
            }

        except subprocess.TimeoutExpired:
            process.kill()
            return {
                "ok": True,
                "log": "Backend started successfully.",
            }

    except Exception as e:
        return {
            "ok": False,
            "log": str(e),
        }


def clean_frontend_dependencies(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    app_file = os.path.join(project_path, "frontend", "src", "App.jsx")
    package_file = os.path.join(project_path, "frontend", "package.json")

    removed_items = []
    blocked_dependencies = [
        "@heroicons/react",
        "lucide-react",
        "framer-motion",
        "@mui/material",
        "@emotion/react",
        "@emotion/styled",
    ]

    if os.path.exists(package_file):
        with open(package_file, "r", encoding="utf-8") as f:
            package_data = json.load(f)

        for section in ["dependencies", "devDependencies"]:
            deps = package_data.get(section, {})

            for dep in blocked_dependencies:
                if dep in deps:
                    del deps[dep]
                    removed_items.append(f"package.json: {dep}")

            package_data[section] = deps

        with open(package_file, "w", encoding="utf-8") as f:
            json.dump(package_data, f, indent=4)

    if os.path.exists(app_file):
        with open(app_file, "r", encoding="utf-8") as f:
            code = f.read()

        for dep in blocked_dependencies:
            if dep in code:
                removed_items.append(f"App.jsx import: {dep}")

        lines = code.splitlines()
        cleaned_lines = []

        for line in lines:
            if any(dep in line for dep in blocked_dependencies):
                continue
            cleaned_lines.append(line)

        code = "\n".join(cleaned_lines)

        icon_replacements = {
            "<PlusIcon": "<span",
            "</PlusIcon>": "</span>",
            "<TrashIcon": "<span",
            "</TrashIcon>": "</span>",
            "<UserIcon": "<span",
            "</UserIcon>": "</span>",
            "<PencilIcon": "<span",
            "</PencilIcon>": "</span>",
            "<CheckIcon": "<span",
            "</CheckIcon>": "</span>",
            "<XMarkIcon": "<span",
            "</XMarkIcon>": "</span>",
        }

        for old, new in icon_replacements.items():
            code = code.replace(old, new)

        with open(app_file, "w", encoding="utf-8") as f:
            f.write(code)

    log_project_activity(
        project_name,
        "FRONTEND_DEPENDENCIES_CLEANED",
        f"Removed:\n{chr(10).join(removed_items) if removed_items else 'None'}",
    )

    return f"""
FRONTEND DEPENDENCY CLEAN COMPLETE

PROJECT:
{project_name}

REMOVED:
{chr(10).join(removed_items) if removed_items else "None"}
"""


def validate_sqlite_runtime(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    backend_path = os.path.join(project_path, "backend")
    database_file = os.path.abspath(os.path.join(backend_path, "database.py"))
    db_file = os.path.abspath(os.path.join(backend_path, "app.db"))
    results = []

    if not os.path.exists(database_file):
        return "backend/database.py not found."

    try:
        old_cwd = os.getcwd()
        os.chdir(backend_path)

        spec = importlib.util.spec_from_file_location(
            "runtime_database_check",
            database_file,
        )

        database_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(database_module)

        if hasattr(database_module, "init_db"):
            database_module.init_db()
            results.append("PASS: init_db() executed successfully")
        else:
            results.append("FAIL: init_db() not found in database.py")

        os.chdir(old_cwd)

    except Exception as e:
        try:
            os.chdir(old_cwd)
        except Exception:
            pass

        results.append(f"FAIL: init_db() failed: {e}")

    if not os.path.exists(db_file):
        results.append("FAIL: app.db was not created")
    else:
        results.append("PASS: app.db exists")

        try:
            connection = sqlite3.connect(db_file)
            cursor = connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            table = cursor.fetchone()

            if table:
                results.append("PASS: items table exists in app.db")
                cursor.execute("PRAGMA table_info(items)")
                columns = [row[1] for row in cursor.fetchall()]

                required_columns = ["id", "title", "description", "email", "phone"]

                for column in required_columns:
                    if column in columns:
                        results.append(f"PASS: SQLite column exists: {column}")
                    else:
                        results.append(f"FAIL: SQLite column missing: {column}")
            else:
                results.append("FAIL: items table missing in app.db")

            connection.close()

        except Exception as e:
            results.append(f"FAIL: SQLite inspection failed: {e}")

    log_project_activity(
        project_name,
        "SQLITE_RUNTIME_VALIDATED",
        "\n".join(results),
    )

    return f"""
SQLITE RUNTIME VALIDATION

PROJECT:
{project_name}

RESULTS:
{chr(10).join(results)}
"""


def fix_sqlite_runtime(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    backend_path = os.path.join(project_path, "backend")
    db_file = os.path.join(backend_path, "app.db")

    if os.path.exists(db_file):
        os.remove(db_file)

    validation_result = validate_sqlite_runtime(project_name)

    log_project_activity(
        project_name,
        "SQLITE_RUNTIME_FIXED",
        "Deleted and recreated app.db using init_db().",
    )

    return f"""
SQLITE RUNTIME FIX COMPLETE

PROJECT:
{project_name}

ACTION:
Deleted old app.db and recreated it from database.py.

====================
NEW VALIDATION
====================
{validation_result}
"""


def quality_fix_project(project_name, patch_code, basic_project_quality_check):
    if get_project_stack_key(project_name) != "react_flask_sqlite":
        return basic_project_quality_check(project_name)

    results = []
    results.append("STEP 1: Preflight")
    results.append(preflight_fullstack_project(project_name))
    results.append("STEP 2: Fix backend imports")
    results.append(fix_backend_imports(project_name))
    results.append("STEP 3: Fix API contract")
    results.append(fix_api_contract(project_name))
    results.append("STEP 4: Fix database schema")
    results.append(fix_database_schema(project_name))
    results.append("STEP 4.1: Fix SQLite runtime")
    results.append(fix_sqlite_runtime(project_name))
    results.append("STEP 4.5: Backend smoke test")

    backend_smoke = smoke_test_backend(project_name)
    results.append(backend_smoke["log"])

    if not backend_smoke["ok"]:
        results.append("Backend smoke test failed. Running targeted backend heal.")
        broken_file = detect_broken_file(backend_smoke["log"])

        if broken_file:
            with open(broken_file, "r", encoding="utf-8") as f:
                broken_code = f.read()

            fixed_code = patch_code(
                broken_code,
                backend_smoke["log"],
            )

            with open(broken_file, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            results.append(f"Healed backend file from smoke test: {broken_file}")

    results.append("STEP 4.6: Clean frontend dependencies")
    results.append(clean_frontend_dependencies(project_name))
    results.append("STEP 5: Run fullstack")
    results.append(run_fullstack_project(project_name))
    results.append("STEP 5.5: Heal fullstack after run")
    results.append(agent_healer.heal_fullstack_project(project_name, patch_code))
    results.append("STEP 6: Test endpoints")
    endpoint_result = test_runtime_endpoints(project_name)
    results.append(endpoint_result)

    if "FAIL:" in endpoint_result:
        final_status = "NEEDS ATTENTION"
    else:
        final_status = "READY"

    log_project_activity(
        project_name,
        "QUALITY_FIX_RUN",
        final_status,
    )

    return f"""
QUALITY FIX REPORT

PROJECT:
{project_name}

FINAL STATUS:
{final_status}

====================
DETAILS
====================
{chr(10).join(results)}
"""


def quality_check_project(project_name, basic_project_quality_check):
    if get_project_stack_key(project_name) != "react_flask_sqlite":
        return basic_project_quality_check(project_name)

    results = []
    results.append("STEP 1: Preflight")
    preflight_result = preflight_fullstack_project(project_name)
    results.append(preflight_result)
    results.append("STEP 2: Backend imports")
    imports_result = validate_backend_imports(project_name)
    results.append(imports_result)
    results.append("STEP 3: API contract")
    contract_result = validate_api_contract(project_name)
    results.append(contract_result)
    results.append("STEP 4: Database schema")
    database_result = validate_database_schema(project_name)
    results.append(database_result)
    results.append("STEP 5: Runtime endpoints")
    endpoint_result = test_runtime_endpoints(project_name)
    results.append(endpoint_result)

    combined = "\n".join(results)

    if "FAIL:" in combined:
        final_status = "NEEDS FIX"
    else:
        final_status = "READY"

    log_project_activity(
        project_name,
        "QUALITY_CHECK_RUN",
        final_status,
    )

    return f"""
QUALITY CHECK REPORT

PROJECT:
{project_name}

FINAL STATUS:
{final_status}

====================
DETAILS
====================
{combined}
"""
