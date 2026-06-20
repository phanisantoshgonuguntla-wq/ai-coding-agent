import json
import os


WORKSPACE_DIR = "workspace"

APP_INTENT_WORDS = [
    "app",
    "application",
    "dashboard",
    "tracker",
    "system",
    "portal",
    "website",
    "crm",
    "todo",
    "notes",
    "inventory",
    "manager",
]


BUILD_INTENT_WORDS = [
    "build",
    "create",
    "make",
    "generate",
    "develop",
    "need",
    "want",
]


SUPPORTED_APP_STACKS = {
    "react_flask_sqlite": {
        "label": "React + Flask + SQLite",
        "aliases": ["flask", "python", "react flask", "react + flask"],
        "frontend_url": "http://127.0.0.1:5173",
        "backend_url": "http://127.0.0.1:5000",
        "required_files": [
            "backend/app.py",
            "backend/routes.py",
            "backend/database.py",
            "backend/models.py",
            "backend/requirements.txt",
            "frontend/package.json",
            "frontend/src/App.jsx",
            "frontend/src/api.js",
        ],
    },
    "react_dotnet_sqlite": {
        "label": "React + ASP.NET Core + SQLite",
        "aliases": [".net", "dotnet", "asp.net", "c#"],
        "frontend_url": "http://127.0.0.1:5173",
        "backend_url": "http://127.0.0.1:5000",
        "required_files": [
            "backend/GeneratedApp.Api.csproj",
            "backend/Program.cs",
            "frontend/package.json",
            "frontend/src/App.jsx",
            "frontend/src/api.js",
        ],
    },
    "react_php_sqlite": {
        "label": "React + PHP + SQLite",
        "aliases": ["php"],
        "frontend_url": "http://127.0.0.1:5173",
        "backend_url": "http://127.0.0.1:8000",
        "required_files": [
            "backend/index.php",
            "backend/database.php",
            "frontend/package.json",
            "frontend/src/App.jsx",
            "frontend/src/api.js",
        ],
    },
}


def detect_requested_stack(user_input):
    text = user_input.lower()

    for stack_key, stack in SUPPORTED_APP_STACKS.items():
        if any(alias in text for alias in stack["aliases"]):
            return stack_key

    return "react_flask_sqlite"


def get_stack(stack_key):
    return SUPPORTED_APP_STACKS.get(stack_key, SUPPORTED_APP_STACKS["react_flask_sqlite"])


def get_project_stack_key(project_name):
    spec_path = os.path.join(WORKSPACE_DIR, project_name, "project_spec.json")

    if not os.path.exists(spec_path):
        return "react_flask_sqlite"

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)

        stack_key = spec.get("stack_key")

        if stack_key in SUPPORTED_APP_STACKS:
            return stack_key

        app_type = spec.get("app_type", "").lower()

        for candidate_key, stack in SUPPORTED_APP_STACKS.items():
            if stack["label"].lower() == app_type:
                return candidate_key

    except Exception:
        pass

    return "react_flask_sqlite"


def build_stack_instruction(stack_key, project_config=None):
    stack = get_stack(stack_key)
    project_config = project_config or {
        "frontend_url": stack["frontend_url"],
        "backend_url": stack["backend_url"],
        "frontend_port": stack["frontend_url"].rsplit(":", 1)[-1],
        "backend_port": stack["backend_url"].rsplit(":", 1)[-1],
    }
    frontend_url = project_config["frontend_url"]
    backend_url = project_config["backend_url"]
    backend_port = project_config["backend_port"]

    if stack_key == "react_dotnet_sqlite":
        return f"""
STRICT FORMAT:

file: backend/GeneratedApp.Api.csproj
<xml>

file: backend/Program.cs
<csharp code>

file: frontend/package.json
<json>

file: frontend/index.html
<html>

file: frontend/src/main.jsx
<jsx>

file: frontend/src/App.jsx
<jsx>

file: frontend/src/api.js
<javascript>

file: frontend/src/style.css
<css>

Rules:
- Backend must use ASP.NET Core Minimal API
- Backend must use SQLite through Microsoft.Data.Sqlite
- Backend must expose JSON API routes at /api/items
- Backend must enable CORS for {frontend_url}
- Backend must run on {backend_url}
- Frontend must use React + Vite and fetch
- Frontend must call backend API at {backend_url}
- Keep code simple and runnable
"""

    if stack_key == "react_php_sqlite":
        return f"""
STRICT FORMAT:

file: backend/index.php
<php code>

file: backend/database.php
<php code>

file: frontend/package.json
<json>

file: frontend/index.html
<html>

file: frontend/src/main.jsx
<jsx>

file: frontend/src/App.jsx
<jsx>

file: frontend/src/api.js
<javascript>

file: frontend/src/style.css
<css>

Rules:
- Backend must use plain PHP
- Backend must use SQLite through PDO
- Backend must expose JSON API routes at /api/items
- Backend must handle CORS and OPTIONS requests
- Backend must run with php -S 127.0.0.1:{backend_port} -t backend
- Frontend must use React + Vite and fetch
- Frontend must call backend API at {backend_url}
- Keep code simple and runnable
"""

    return f"""
STRICT FORMAT:

file: backend/app.py
<python code>

file: backend/routes.py
<python code>

file: backend/database.py
<python code>

file: backend/models.py
<python code>

file: backend/requirements.txt
<requirements>

file: frontend/package.json
<json>

file: frontend/index.html
<html>

file: frontend/src/main.jsx
<jsx>

file: frontend/src/App.jsx
<jsx>

file: frontend/src/api.js
<javascript>

file: frontend/src/style.css
<css>

Rules:
- Backend must use Flask
- Backend must use sqlite3 only
- Backend must expose JSON API routes
- Backend must handle CORS manually, do not use flask_cors
- Backend must run on {backend_url}
- Frontend must use React + Vite
- Frontend must call backend API at {backend_url}
- Do NOT use external UI libraries
- Do NOT use @heroicons/react
- Do NOT use lucide-react
- Do NOT use framer-motion
- Do NOT use Material UI or MUI
- Do NOT use Tailwind CSS
- Use only React, ReactDOM, Vite, plain CSS, and fetch
- Do not import any frontend package that is not listed in package.json
- package.json must only contain react, react-dom, vite, and @vitejs/plugin-react
- Keep code simple and runnable
"""


def looks_like_app_build_request(user_input):
    text = user_input.lower()
    has_app_word = any(word in text for word in APP_INTENT_WORDS)
    has_build_word = any(word in text for word in BUILD_INTENT_WORDS)
    return has_app_word and has_build_word


def list_supported_stacks():
    lines = []

    for stack_key, stack in SUPPORTED_APP_STACKS.items():
        lines.append(f"- {stack_key}: {stack['label']}")

    return "Supported app stacks:\n\n" + "\n".join(lines)


def get_stack_build_steps(stack_key):
    if stack_key == "react_dotnet_sqlite":
        return [
            "Create ASP.NET Core Minimal API backend",
            "Create SQLite persistence with Microsoft.Data.Sqlite",
            "Create React Vite frontend",
            "Connect frontend fetch calls to assigned backend URL",
            "Run frontend build and backend API validation"
        ]

    if stack_key == "react_php_sqlite":
        return [
            "Create plain PHP JSON API backend",
            "Create SQLite persistence with PDO",
            "Create React Vite frontend",
            "Connect frontend fetch calls to assigned backend URL",
            "Run frontend build and backend API validation"
        ]

    return [
        "Create Flask JSON API backend",
        "Create SQLite persistence with sqlite3",
        "Create React Vite frontend",
        "Connect frontend fetch calls to assigned backend URL",
        "Run frontend build and backend API validation"
    ]
