import os
import re
import json
import time
import subprocess
import sys
import sqlite3

import agent_builder
import agent_llm
from agent_llm import (
    get_ollama_models,
    invoke_llm,
    is_ollama_available,
    is_ollama_model_installed,
    ollama_memory_error_message,
    ollama_model_missing_message,
    ollama_unavailable_message,
)
from agent_stacks import (
    SUPPORTED_APP_STACKS,
    build_stack_instruction,
    detect_requested_stack,
    get_project_stack_key,
    get_stack,
    get_stack_build_steps,
    list_supported_stacks,
    looks_like_app_build_request,
)
from agent_text import clean_code_output, make_safe_project_name, strip_command_prefix
from agent_project_files import (
    detect_broken_file,
    find_python_syntax_error,
    parse_llm_project_output,
    write_project,
)
from agent_planner import (
    create_app_plan,
    create_fallback_project_spec,
    is_fallback_description,
    normalize_project_spec,
    plan_app,
    refresh_project_spec,
    save_project_spec,
)

from tools import (
    run_project_file,
    extract_error_summary,
    run_fullstack_project,
    stop_fullstack_project,
    stop_all_fullstack_projects,
    validate_generated_app,
    show_fullstack_logs,
    get_fullstack_logs,
    install_python_package,
    install_npm_package,
    detect_missing_python_package,
    detect_missing_npm_package,
    restart_fullstack_project,
    create_project_snapshot,
    list_project_snapshots,
    restore_project_snapshot,
    compare_project_snapshot,
    restore_missing_project_files,
    get_project_history,
    log_project_activity,
    restore_changed_project_files,
    preflight_fullstack_project,
    ensure_project_config,
    reset_project_database
)

WORKSPACE_DIR = "workspace"
OLLAMA_BASE_URL = agent_llm.OLLAMA_BASE_URL
OLLAMA_MODEL = agent_llm.OLLAMA_MODEL


def set_ollama_model(model_name):
    global OLLAMA_MODEL

    OLLAMA_MODEL = agent_llm.set_ollama_model(model_name)
    return OLLAMA_MODEL


AGENT_HELP_TEXT = """
AI Coding Agent commands:

- create app <requirement>
  Plan, build, heal, quality-check, and snapshot a React + Flask + SQLite app.

- plan app <requirement>
  Create only the project_spec.json plan.

- build from plan <project_name>
  Build an app from an existing workspace/<project_name>/project_spec.json.

- run fullstack <project_name>
  Start the backend and frontend dev servers.

- show logs <project_name>
  Show captured backend and frontend logs.

- modify app <project_name> <change request>
  Update an existing app from a change request.

- add feature <project_name> <feature request>
  Add a feature to an existing app.

- quality check <project_name>
  Inspect generated project quality.

- validate app <project_name>
  Run stack-aware file, build, API, database, and frontend runtime checks.

- supported stacks
  List app stacks this builder can generate.

- refresh project ports <project_name>
  Create/update project_config.json and rewrite local run URLs.

- refresh project spec <project_name>
  Normalize project_spec.json with stack-aware fields, routes, URLs, and build steps.

- stop all apps
  Stop running generated app backends/frontends on assigned project ports.

- reset database <project_name>
  Stop the selected app and delete its local SQLite database file.
"""


def create_standalone_project_files(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    stack_key = get_project_stack_key(project_name)
    stack = get_stack(stack_key)
    project_config = ensure_project_config(project_name, stack_key)
    frontend_url = project_config["frontend_url"]
    backend_url = project_config["backend_url"]
    frontend_port = project_config["frontend_port"]
    backend_port = project_config["backend_port"]

    os.makedirs(project_path, exist_ok=True)

    if stack_key == "react_dotnet_sqlite":
        backend_commands = [
            "cd backend",
            "dotnet restore",
            f"dotnet run --urls {backend_url}",
        ]
        backend_script = f'@echo off\ncd /d "%~dp0backend"\ndotnet restore\ndotnet run --urls {backend_url}\n'
    elif stack_key == "react_php_sqlite":
        backend_commands = [
            f"php -S 127.0.0.1:{backend_port} -t backend",
        ]
        backend_script = f'@echo off\ncd /d "%~dp0"\nphp -S 127.0.0.1:{backend_port} -t backend\n'
    else:
        backend_commands = [
            "cd backend",
            "python -m pip install -r requirements.txt",
            "python app.py",
        ]
        backend_script = '@echo off\ncd /d "%~dp0backend"\npython -m pip install -r requirements.txt\npython app.py\n'

    frontend_script = f'@echo off\ncd /d "%~dp0frontend"\nnpm install\nnpm run dev -- --host 127.0.0.1 --port {frontend_port}\n'

    readme = f"""# {project_name}

Generated standalone application.

Stack: {stack["label"]}

This app can run without `agent.py`, `tools.py`, or the Streamlit builder UI. Those files are only needed when you want the AI builder to create, modify, heal, or inspect generated projects.

## Backend

```text
{chr(10).join(backend_commands)}
```

Backend URL: {backend_url}

## Frontend

```text
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port {frontend_port}
```

Frontend URL: {frontend_url}

## Windows shortcuts

- Double-click `run_backend.bat`
- Double-click `run_frontend.bat`
"""

    files = {
        "README.md": readme,
        "run_backend.bat": backend_script,
        "run_frontend.bat": frontend_script,
    }

    for file_name, content in files.items():
        file_path = os.path.join(project_path, file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    log_project_activity(
        project_name,
        "STANDALONE_FILES_CREATED",
        "Created README.md, run_backend.bat, and run_frontend.bat"
    )

    return list(files.keys())


def create_dotnet_fallback_files():
    return {
        "backend/GeneratedApp.Api.csproj": """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.Data.Sqlite" Version="8.0.0" />
  </ItemGroup>
</Project>
""",
        "backend/Program.cs": """using Microsoft.Data.Sqlite;

var builder = WebApplication.CreateBuilder(args);

builder.WebHost.UseUrls("http://127.0.0.1:5000");
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy
            .WithOrigins("http://127.0.0.1:5173")
            .AllowAnyHeader()
            .AllowAnyMethod();
    });
});

var app = builder.Build();

app.UseCors();

const string connectionString = "Data Source=app.db";

static void InitDb(string connectionString)
{
    using var connection = new SqliteConnection(connectionString);
    connection.Open();

    using var command = connection.CreateCommand();
    command.CommandText = @"
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT
        );
    ";
    command.ExecuteNonQuery();
}

InitDb(connectionString);

app.MapGet("/api/items", () =>
{
    var items = new List<Item>();

    using var connection = new SqliteConnection(connectionString);
    connection.Open();

    using var command = connection.CreateCommand();
    command.CommandText = "SELECT id, title, description FROM items ORDER BY id DESC";

    using var reader = command.ExecuteReader();
    while (reader.Read())
    {
        items.Add(new Item(
            reader.GetInt32(0),
            reader.GetString(1),
            reader.IsDBNull(2) ? "" : reader.GetString(2)
        ));
    }

    return Results.Ok(items);
});

app.MapPost("/api/items", (ItemInput input) =>
{
    if (string.IsNullOrWhiteSpace(input.Title))
    {
        return Results.BadRequest(new { error = "title is required" });
    }

    using var connection = new SqliteConnection(connectionString);
    connection.Open();

    using var command = connection.CreateCommand();
    command.CommandText = @"
        INSERT INTO items (title, description)
        VALUES ($title, $description);
    ";
    command.Parameters.AddWithValue("$title", input.Title.Trim());
    command.Parameters.AddWithValue("$description", input.Description ?? "");
    command.ExecuteNonQuery();

    return Results.Created("/api/items", new { message = "item added" });
});

app.Run();

record Item(int Id, string Title, string Description);
record ItemInput(string Title, string? Description);
""",
        "frontend/package.json": """{
  "name": "generated-notes-app",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "@vitejs/plugin-react": "latest",
    "vite": "latest",
    "react": "latest",
    "react-dom": "latest"
  },
  "devDependencies": {}
}
""",
        "frontend/index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Notes App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
""",
        "frontend/src/main.jsx": """import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./style.css";

createRoot(document.getElementById("root")).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);
""",
        "frontend/src/api.js": """const API_URL = "http://127.0.0.1:5000/api/items";

export async function getItems() {
    const response = await fetch(API_URL);

    if (!response.ok) {
        throw new Error("Could not load notes");
    }

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

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || "Could not add note");
    }

    return response.json();
}
""",
        "frontend/src/App.jsx": """import { useEffect, useState } from "react";
import { addItem, getItems } from "./api.js";

export default function App() {
    const [items, setItems] = useState([]);
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [error, setError] = useState("");

    async function loadItems() {
        try {
            const data = await getItems();
            setItems(data);
            setError("");
        } catch (err) {
            setError(err.message);
        }
    }

    async function handleSubmit(event) {
        event.preventDefault();
        setError("");

        if (!title.trim()) {
            setError("Title is required.");
            return;
        }

        try {
            await addItem({ title, description });
            setTitle("");
            setDescription("");
            await loadItems();
        } catch (err) {
            setError(err.message);
        }
    }

    useEffect(() => {
        loadItems();
    }, []);

    return (
        <main>
            <h1>Notes App</h1>

            <form onSubmit={handleSubmit}>
                <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Title"
                />
                <textarea
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="Description"
                />
                <button type="submit">Add note</button>
            </form>

            {error && <p className="error">{error}</p>}

            <ul>
                {items.map((item) => (
                    <li key={item.id}>
                        <strong>{item.title}</strong>
                        {item.description && <p>{item.description}</p>}
                    </li>
                ))}
            </ul>
        </main>
    );
}
""",
        "frontend/src/style.css": """body {
    margin: 0;
    background: #f3f5f7;
    color: #1f2933;
    font-family: Arial, sans-serif;
}

main {
    max-width: 760px;
    margin: 40px auto;
    padding: 24px;
    background: #ffffff;
    border: 1px solid #dde3ea;
    border-radius: 8px;
}

h1 {
    margin-top: 0;
}

form {
    display: grid;
    gap: 12px;
    margin: 16px 0;
}

input,
textarea {
    box-sizing: border-box;
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #c8d1dc;
    border-radius: 6px;
    font: inherit;
}

textarea {
    min-height: 96px;
    resize: vertical;
}

button {
    width: fit-content;
    padding: 10px 16px;
    border: 0;
    border-radius: 6px;
    background: #0f766e;
    color: #ffffff;
    cursor: pointer;
    font-weight: 700;
}

.error {
    padding: 10px 12px;
    border: 1px solid #f3b4b4;
    border-radius: 6px;
    background: #fff1f2;
    color: #9f1239;
}

ul {
    list-style: none;
    padding: 0;
}

li {
    margin: 12px 0;
    padding: 14px;
    border: 1px solid #dde3ea;
    border-radius: 8px;
    background: #fbfcfd;
}

li p {
    overflow-wrap: anywhere;
}
"""
    }


def create_php_fallback_files():
    return {
        "backend/database.php": """<?php
function get_connection() {
    $db = new PDO("sqlite:" . __DIR__ . "/app.db");
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $db->exec("CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT
    )");
    return $db;
}
""",
        "backend/index.php": """<?php
require_once __DIR__ . "/database.php";

header("Access-Control-Allow-Origin: http://127.0.0.1:5173");
header("Access-Control-Allow-Headers: Content-Type");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Content-Type: application/json");

if ($_SERVER["REQUEST_METHOD"] === "OPTIONS") {
    http_response_code(200);
    echo json_encode([]);
    exit;
}

$path = parse_url($_SERVER["REQUEST_URI"], PHP_URL_PATH);

if ($path !== "/api/items") {
    http_response_code(404);
    echo json_encode(["error" => "not found"]);
    exit;
}

$db = get_connection();

if ($_SERVER["REQUEST_METHOD"] === "GET") {
    $statement = $db->query("SELECT id, title, description FROM items ORDER BY id DESC");
    echo json_encode($statement->fetchAll(PDO::FETCH_ASSOC));
    exit;
}

if ($_SERVER["REQUEST_METHOD"] === "POST") {
    $data = json_decode(file_get_contents("php://input"), true) ?: [];
    $title = trim($data["title"] ?? "");
    $description = $data["description"] ?? "";

    if ($title === "") {
        http_response_code(400);
        echo json_encode(["error" => "title is required"]);
        exit;
    }

    $statement = $db->prepare("INSERT INTO items (title, description) VALUES (:title, :description)");
    $statement->execute([
        ":title" => $title,
        ":description" => $description
    ]);

    http_response_code(201);
    echo json_encode(["message" => "item added"]);
    exit;
}

http_response_code(405);
echo json_encode(["error" => "method not allowed"]);
""",
        **create_dotnet_fallback_files(),
    }


def create_fallback_project_files(stack_key):
    if stack_key == "react_dotnet_sqlite":
        return create_dotnet_fallback_files()

    if stack_key == "react_php_sqlite":
        php_files = create_php_fallback_files()
        filtered_files = {
            key: value
            for key, value in php_files.items()
            if not key.endswith(".csproj") and key != "backend/Program.cs"
        }
        filtered_files["frontend/src/api.js"] = filtered_files["frontend/src/api.js"].replace(
            "http://127.0.0.1:5000/api/items",
            "http://127.0.0.1:8000/api/items"
        )
        return filtered_files

    return {}


def apply_project_ports_to_files(files_dict, project_config, stack_key):
    backend_url = project_config["backend_url"]
    frontend_url = project_config["frontend_url"]
    frontend_port = str(project_config["frontend_port"])
    backend_port = str(project_config["backend_port"])

    replacements = {
        "http://127.0.0.1:5000": backend_url,
        "http://localhost:5000": backend_url,
        "http://127.0.0.1:8000": backend_url,
        "http://localhost:8000": backend_url,
        "http://127.0.0.1:5173": frontend_url,
        "http://localhost:5173": frontend_url,
        "--port 5173": f"--port {frontend_port}",
        "127.0.0.1:5000": f"127.0.0.1:{backend_port}",
        "127.0.0.1:8000": f"127.0.0.1:{backend_port}",
        "127.0.0.1:5173": f"127.0.0.1:{frontend_port}",
    }

    normalized = {}

    for file_name, content in files_dict.items():
        updated_content = content

        for old, new in replacements.items():
            updated_content = updated_content.replace(old, new)

        normalized[file_name] = updated_content

    return normalized


def refresh_project_ports(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    stack_key = get_project_stack_key(project_name)
    project_config = ensure_project_config(project_name, stack_key)
    relative_files = [
        "backend/app.py",
        "backend/Program.cs",
        "backend/index.php",
        "frontend/src/api.js",
    ]
    files_to_update = {}

    for relative_file in relative_files:
        file_path = os.path.join(project_path, relative_file)

        if not os.path.exists(file_path):
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            files_to_update[relative_file] = f.read()

    updated_files = apply_project_ports_to_files(
        files_to_update,
        project_config,
        stack_key
    )

    changed_files = []

    for relative_file, updated_content in updated_files.items():
        file_path = os.path.join(project_path, relative_file)

        if files_to_update[relative_file] == updated_content:
            continue

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        changed_files.append(relative_file)

    standalone_files = create_standalone_project_files(project_name)

    log_project_activity(
        project_name,
        "PROJECT_PORTS_REFRESHED",
        f"Changed files:\n{chr(10).join(changed_files) if changed_files else 'None'}"
    )

    return f"""
PROJECT PORTS REFRESHED

PROJECT:
{project_name}

FRONTEND:
{project_config["frontend_url"]}

BACKEND:
{project_config["backend_url"]}

UPDATED CODE FILES:
{chr(10).join(changed_files) if changed_files else "None"}

STANDALONE FILES:
{chr(10).join(standalone_files)}
"""


def generate_flask_project(user_input):
    prompt = f"""
You are a Flask web app generator.

Generate ONLY raw project files.

STRICT FORMAT:

file: app.py
<python code>

file: routes.py
<python code>

file: database.py
<python code>

file: models.py
<python code>

file: templates/layout.html
<html code>

file: templates/index.html
<html code>

file: static/style.css
<css code>

file: requirements.txt
<requirements>

Rules:
- No explanation
- No markdown
- Every file MUST start with file:
- Use sqlite3 from Python standard library
- database.py must create and return SQLite connections
- models.py must contain database functions
- routes.py must use register_routes(app)
- app.py must import register_routes and call register_routes(app)
- app.py must call init_db() before running
- requirements.txt must contain flask
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

User request:
{user_input}
"""
    return invoke_llm(prompt)


def generate_fullstack_project(user_input):
    prompt = f"""
You are a full-stack Flask API + React Vite generator.

Generate ONLY raw project files.

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
- No explanation
- No markdown
- Every file MUST start with file:
- Backend must use Flask
- Backend must use sqlite3 only
- Backend must expose JSON API routes
- Backend routes must support GET and POST
- Backend must enable CORS manually by adding response headers, do not use flask_cors
- Frontend must use React with Vite
- Frontend must fetch API from http://127.0.0.1:5000
- Keep code simple and runnable

User request:
{user_input}
"""
    return invoke_llm(prompt)


def patch_code(original_code, error_summary):
    prompt = f"""
Fix ONLY the broken Python syntax or smallest broken section.

Return the COMPLETE corrected file code.

ERROR:
{error_summary}

CODE:
{original_code}

PROJECT RULES:
- Use sqlite3 only for database work
- Never use flask_sqlalchemy
- Never use SQLAlchemy
- Never introduce new dependencies unless requirements.txt is updated

Rules:
- Preserve existing working code
- Remove invalid non-Python text if present
- Return only valid Python code
- No markdown
- No explanation
"""
    return clean_code_output(invoke_llm(prompt))


def validate_flask_structure(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    fixes = []

    required_files = {
        "app.py": """
from flask import Flask
from routes import register_routes
from database import init_db

app = Flask(__name__)

init_db()
register_routes(app)

if __name__ == "__main__":
    app.run(debug=True)
""",
        "database.py": """
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
            title TEXT NOT NULL
        )
    \"\"\")

    connection.commit()
    connection.close()
""",
        "models.py": """
from database import get_connection

def get_items():
    connection = get_connection()
    items = connection.execute("SELECT id, title FROM items ORDER BY id DESC").fetchall()
    connection.close()
    return items

def add_item(title):
    connection = get_connection()
    connection.execute("INSERT INTO items (title) VALUES (?)", (title,))
    connection.commit()
    connection.close()

def delete_item(item_id):
    connection = get_connection()
    connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
    connection.commit()
    connection.close()
""",
        "routes.py": """
from flask import render_template, request, redirect, url_for
from models import get_items, add_item, delete_item

def register_routes(app):

    @app.route("/")
    def index():
        items = get_items()
        return render_template("index.html", items=items)

    @app.route("/add", methods=["POST"])
    def add():
        title = request.form.get("title")

        if title:
            add_item(title)

        return redirect(url_for("index"))

    @app.route("/delete/<int:item_id>")
    def delete(item_id):
        delete_item(item_id)
        return redirect(url_for("index"))
""",
        "templates/layout.html": """
<!DOCTYPE html>
<html>
<head>
    <title>SQLite Flask App</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
""",
        "templates/index.html": """
{% extends "layout.html" %}

{% block content %}
<h1>SQLite Flask App</h1>

<form method="POST" action="{{ url_for('add') }}">
    <input type="text" name="title" placeholder="Enter item" required>
    <button type="submit">Add</button>
</form>

<ul>
    {% for item in items %}
        <li>
            {{ item["title"] }}
            <a href="{{ url_for('delete', item_id=item['id']) }}">Delete</a>
        </li>
    {% endfor %}
</ul>
{% endblock %}
""",
        "static/style.css": """
body {
    font-family: Arial, sans-serif;
    background: #f5f5f5;
    margin: 40px;
}

main {
    max-width: 700px;
    margin: auto;
    background: white;
    padding: 24px;
    border-radius: 12px;
}
""",
        "requirements.txt": "flask\n"
    }

    for file_name, default_content in required_files.items():
        full_path = os.path.join(project_path, file_name)

        if not os.path.exists(full_path):
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(default_content.strip())
            fixes.append(file_name)

    return fixes


def validate_fullstack_structure(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    fixes = []
    project_config = ensure_project_config(project_name, "react_flask_sqlite")

    required_files = {
        "backend/app.py": """
import os
from flask import Flask
from routes import register_routes
from database import init_db

app = Flask(__name__)

init_db()
register_routes(app)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)
""",
        "backend/database.py": """
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
            title TEXT NOT NULL
        )
    \"\"\")

    connection.commit()
    connection.close()
""",
        "backend/models.py": """
from database import get_connection

def get_items():
    connection = get_connection()
    items = connection.execute("SELECT id, title FROM items ORDER BY id DESC").fetchall()
    connection.close()
    return [dict(item) for item in items]

def add_item(title):
    connection = get_connection()
    connection.execute("INSERT INTO items (title) VALUES (?)", (title,))
    connection.commit()
    connection.close()
""",
        "backend/routes.py": """
from flask import request, jsonify
from models import get_items, add_item

def register_routes(app):

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response

    @app.route("/todo", methods=["GET"])
    def list_todos():
        return jsonify(get_items())

    @app.route("/todo", methods=["POST", "OPTIONS"])
    def create_todo():
        if request.method == "OPTIONS":
            return jsonify({}), 200

        data = request.get_json() or {}
        title = data.get("title")

        if not title:
            return jsonify({"error": "title is required"}), 400

        add_item(title)
        return jsonify({"message": "item added"}), 201
""",
        "backend/requirements.txt": "flask\n",
        "frontend/package.json": """
{
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "@vitejs/plugin-react": "latest",
    "vite": "latest",
    "react": "latest",
    "react-dom": "latest"
  },
  "devDependencies": {}
}
""",
        "frontend/index.html": """
<!DOCTYPE html>
<html>
<head>
    <title>React Flask App</title>
</head>
<body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
</body>
</html>
""",
        "frontend/src/main.jsx": """
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./style.css";

createRoot(document.getElementById("root")).render(<App />);
""",
        "frontend/src/api.js": """
const API_URL = "__BACKEND_URL__/api/items";

export async function getItems() {
    const response = await fetch(API_URL);
    return response.json();
}

export async function addItem(title) {
    const response = await fetch(API_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ title })
    });

    return response.json();
}
""".replace("__BACKEND_URL__", project_config["backend_url"]),
        "frontend/src/App.jsx": """
import { useEffect, useState } from "react";
import { getItems, addItem } from "./api.js";

export default function App() {
    const [items, setItems] = useState([]);
    const [title, setTitle] = useState("");

    async function loadItems() {
        const data = await getItems();
        setItems(data);
    }

    async function handleSubmit(event) {
        event.preventDefault();

        if (!title.trim()) {
            return;
        }

        await addItem(title);
        setTitle("");
        loadItems();
    }

    useEffect(() => {
        loadItems();
    }, []);

    return (
        <main>
            <h1>React + Flask App</h1>

            <form onSubmit={handleSubmit}>
                <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Add item"
                />
                <button type="submit">Add</button>
            </form>

            <ul>
                {items.map((item) => (
                    <li key={item.id}>{item.title}</li>
                ))}
            </ul>
        </main>
    );
}
""",
        "frontend/src/style.css": """
body {
    font-family: Arial, sans-serif;
    background: #f5f5f5;
    margin: 40px;
}

main {
    max-width: 700px;
    margin: auto;
    background: white;
    padding: 24px;
    border-radius: 12px;
}

input {
    padding: 8px;
    width: 70%;
}

button {
    padding: 8px 12px;
    margin-left: 8px;
}

li {
    margin: 10px 0;
}
""".replace("__BACKEND_URL__", project_config["backend_url"]),
    }

    for file_name, default_content in required_files.items():
        full_path = os.path.join(project_path, file_name)

        if not os.path.exists(full_path):
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(default_content.strip())
            fixes.append(file_name)

    return fixes


def self_heal_project(project_name, entry_file):
    max_attempts = 5
    healed_files = []

    structure_fixes = validate_flask_structure(project_name)
    healed_files.extend(structure_fixes)

    for attempt in range(max_attempts):
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

        print("FULL LOG:\n", result["combined"])

        if result["returncode"] == 0:
            return f"""
âœ… PROJECT RUN SUCCESSFUL

HEALED FILES:
{chr(10).join(healed_files)}

OUTPUT:
{result["combined"]}
"""

        broken_file = detect_broken_file(result["combined"])

        if not broken_file:
            return f"""
âŒ AUTO HEAL FAILED

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
âŒ AUTO HEAL FAILED AFTER {max_attempts} ATTEMPTS
"""

def detect_frontend_broken_file(frontend_logs, project_name):

    project_path = os.path.join(
        WORKSPACE_DIR,
        project_name,
        "frontend",
        "src"
    )

    possible_files = [
        "App.jsx",
        "api.js",
        "main.jsx",
        "style.css"
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

    # Safety guard: if model returns file path instead of code, keep original
    if fixed.strip().replace("\\", "/").endswith(file_name.replace("\\", "/")):
        return original_code

    if fixed.strip().startswith("workspace\\") or fixed.strip().startswith("workspace/"):
        return original_code

    return fixed


def heal_fullstack_project(project_name):

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
            project_name
        )

        installed_packages.append(f"Python: {missing_python_package}")
        actions.append(f"Installed Python package: {missing_python_package}")

        log_project_activity(
            project_name,
            "PYTHON_PACKAGE_INSTALLED",
            missing_python_package
        )

        restart_fullstack_project(project_name)

        return f"""
âœ… FULLSTACK HEAL COMPLETE

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
            missing_npm_package
        )

        installed_packages.append(f"NPM: {missing_npm_package}")
        actions.append(f"Installed NPM package: {missing_npm_package}")

        log_project_activity(
            project_name,
            "NPM_PACKAGE_INSTALLED",
            missing_npm_package
        )

        restart_fullstack_project(project_name)

        return f"""
âœ… FULLSTACK HEAL COMPLETE

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
                    backend_logs
                )

                with open(broken_file, "w", encoding="utf-8") as f:
                    f.write(fixed_code)

                healed_files.append(broken_file)
                actions.append(f"Healed backend file: {broken_file}")

                log_project_activity(
                    project_name,
                    "BACKEND_FILE_HEALED",
                    broken_file
                )

                restart_fullstack_project(project_name)

                return f"""
âœ… FULLSTACK HEAL COMPLETE

ACTIONS:
{chr(10).join(actions)}

INSTALLED PACKAGES:
None

HEALED FILES:
{chr(10).join(healed_files)}
"""

            except Exception as e:
                return f"""
âŒ BACKEND HEAL FAILED

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
            project_name
        )

        if not broken_frontend_file:
            return f"""
âš ï¸ FRONTEND ERROR DETECTED

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
                broken_frontend_file
            )

            with open(broken_frontend_file, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            healed_files.append(broken_frontend_file)
            actions.append(f"Healed frontend file: {broken_frontend_file}")

            log_project_activity(
                project_name,
                "FRONTEND_FILE_HEALED",
                broken_frontend_file
            )

            restart_fullstack_project(project_name)

            return f"""
âœ… FULLSTACK HEAL COMPLETE

ACTIONS:
{chr(10).join(actions)}

INSTALLED PACKAGES:
None

HEALED FILES:
{chr(10).join(healed_files)}
"""

        except Exception as e:
            return f"""
âŒ FRONTEND HEAL FAILED

FILE:
{broken_frontend_file}

ERROR:
{e}
"""

    return """
âœ… NO HEALING NEEDED

No backend or frontend errors found in logs.
"""

def collect_project_code(project_name):

    project_path = os.path.join(WORKSPACE_DIR, project_name)

    important_files = [
        "app.py",
        "routes.py",
        "database.py",
        "models.py",
        "App.jsx",
        "api.js",
        "main.jsx",
        "package.json",
        "requirements.txt"
    ]

    allowed_extensions = [
        ".py",
        ".js",
        ".jsx",
        ".json",
        ".html",
        ".css",
        ".txt",
        ".md"
    ]

    ignored_folders = [
        "node_modules",
        "__pycache__",
        ".git",
        "venv",
        ".venv",
        "dist",
        ".vite"
    ]

    collected = []

    for root, dirs, files in os.walk(project_path):

        dirs[:] = [
            d for d in dirs
            if d not in ignored_folders
        ]

        for file in files:

            if file not in important_files:
                continue

            if not any(file.endswith(ext) for ext in allowed_extensions):
                continue

            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                    if len(content) > 5000:
                        content = content[:5000] + "\n\n...FILE TRUNCATED..."

                relative_path = os.path.relpath(file_path, project_path)

                collected.append(
                    f"""
FILE: {relative_path}
CODE:
{content}
"""
                )

            except Exception:
                continue

    return "\n\n".join(collected)


def review_project(project_name):

    project_code = collect_project_code(project_name)

    if not project_code.strip():
        return "No readable project files found."

    prompt = f"""
You are a senior software engineer reviewing this project.

Review the code and identify:
- bugs
- missing imports
- broken API connections
- dependency issues
- security risks
- bad structure
- improvement suggestions

PROJECT:
{project_name}

CODE:
{project_code}

Return a clear review with:
1. Critical issues
2. Warnings
3. Improvements
4. Suggested next steps
"""

    return invoke_llm(prompt)



def build_from_plan(project_name):
    return agent_builder.build_from_plan(
        project_name,
        create_fallback_project_files,
        apply_project_ports_to_files,
        validate_fullstack_structure,
        create_standalone_project_files,
    )


def basic_project_quality_check(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    stack_key = get_project_stack_key(project_name)
    stack = get_stack(stack_key)
    checks = []
    missing = []

    for relative_path in stack["required_files"]:
        file_path = os.path.join(project_path, relative_path)

        if os.path.exists(file_path):
            checks.append(f"OK: {relative_path}")
        else:
            checks.append(f"MISSING: {relative_path}")
            missing.append(relative_path)

    for relative_path in ["README.md", "run_backend.bat", "run_frontend.bat"]:
        file_path = os.path.join(project_path, relative_path)

        if os.path.exists(file_path):
            checks.append(f"OK: {relative_path}")
        else:
            checks.append(f"MISSING: {relative_path}")
            missing.append(relative_path)

    final_status = "READY" if not missing else "NEEDS ATTENTION"

    log_project_activity(
        project_name,
        "BASIC_QUALITY_CHECK_RUN",
        final_status
    )

    return f"""
BASIC QUALITY CHECK REPORT

PROJECT:
{project_name}

STACK:
{stack["label"]}

FINAL STATUS:
{final_status}

RESULTS:
{chr(10).join(checks)}
"""


def create_app_workflow(user_input):

    requirement = strip_command_prefix(user_input, "create app")

    if not requirement:
        return "Please provide an app requirement."

    project_name = make_safe_project_name(requirement)
    stack_key = detect_requested_stack(requirement)
    stack = get_stack(stack_key)
    project_config = ensure_project_config(project_name, stack_key)

    # 1. Plan
    plan_input = f"plan app {requirement}"
    plan_result = plan_app(plan_input)

    # 2. Build
    build_result = build_from_plan(project_name)

    if stack_key == "react_flask_sqlite":
        # 3. Heal preflight issues first
        preflight_heal_result = heal_preflight_project(project_name)

        # 4. Quality fix
        quality_fix_result = quality_fix_project(project_name)

        # 5. Quality check
        quality_check_result = quality_check_project(project_name)
    else:
        preflight_heal_result = f"Skipped Flask-specific preflight heal for {stack['label']}."
        quality_fix_result = f"Skipped Flask-specific quality fix for {stack['label']}."
        quality_check_result = basic_project_quality_check(project_name)

    # 6. Snapshot
    snapshot_result = create_project_snapshot(project_name)

    if (
        "âŒ" in quality_check_result
        or "NEEDS ATTENTION" in quality_check_result
        or "NEEDS FIX" in quality_check_result
    ):
        final_status = "âŒ NEEDS ATTENTION"
    else:
        final_status = "âœ… READY"

    log_project_activity(
        project_name,
        "CREATE_APP_WORKFLOW_COMPLETE",
        f"Final status: {final_status}"
    )

    return f"""
ðŸš€ CREATE APP WORKFLOW COMPLETE

PROJECT:
workspace/{project_name}

STACK:
{stack["label"]}

FINAL STATUS:
{final_status}

====================
PLAN RESULT
====================
{plan_result}

====================
BUILD RESULT
====================
{build_result}

====================
PREFLIGHT HEAL RESULT
====================
{preflight_heal_result}

====================
QUALITY FIX RESULT
====================
{quality_fix_result}

====================
QUALITY CHECK RESULT
====================
{quality_check_result}

====================
SNAPSHOT RESULT
====================
{snapshot_result}

FRONTEND:
{project_config["frontend_url"]}

BACKEND:
{project_config["backend_url"]}
"""

def heal_preflight_project(project_name):

    preflight_result = preflight_fullstack_project(project_name)

    healed_files = []

    project_path = os.path.join(WORKSPACE_DIR, project_name)

    # Fix Python files from preflight errors
    python_files = [
        "backend/app.py",
        "backend/routes.py",
        "backend/database.py",
        "backend/models.py"
    ]

    for relative_file in python_files:
        file_name = os.path.basename(relative_file)

        if f"âŒ PYTHON ERROR: {file_name}" in preflight_result:
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
                    preflight_result
                )

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            healed_files.append(relative_file)

    # Fix package.json if invalid
    if "package.json invalid JSON" in preflight_result or "package.json missing dev script" in preflight_result:

        package_path = os.path.join(
            project_path,
            "frontend",
            "package.json"
        )

        safe_package_json = {
            "name": "frontend",
            "private": True,
            "version": "0.0.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build"
            },
            "dependencies": {
                "react": "latest",
                "react-dom": "latest"
            },
            "devDependencies": {
                "@vitejs/plugin-react": "latest",
                "vite": "latest"
            }
        }

        with open(package_path, "w", encoding="utf-8") as f:
            json.dump(safe_package_json, f, indent=4)

        healed_files.append("frontend/package.json")

    second_preflight = preflight_fullstack_project(project_name)

    log_project_activity(
        project_name,
        "PREFLIGHT_HEAL_RUN",
        f"Healed files:\n{chr(10).join(healed_files) if healed_files else 'None'}"
    )

    return f"""
ðŸ› ï¸ PREFLIGHT HEAL COMPLETE

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

def validate_api_contract(project_name):

    project_path = os.path.join(WORKSPACE_DIR, project_name)

    api_file = os.path.join(
        project_path,
        "frontend",
        "src",
        "api.js"
    )

    routes_file = os.path.join(
        project_path,
        "backend",
        "routes.py"
    )

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
        api_code
    )

    backend_routes = re.findall(
    r'@app\.route\s*\(\s*["\']([^"\']+)["\']',
    routes_code
    )

    backend_routes += re.findall(
        r'@app\.(get|post|put|delete)\s*\(\s*["\']([^"\']+)["\']',
        routes_code
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
            results.append(
                f"âŒ Frontend calls {route}, but backend route is missing."
            )
    else:
        results.append("âœ… All frontend routes exist in backend.")

    if unused_backend:
        for route in unused_backend:
            results.append(
                f"âš ï¸ Backend route {route} is not used by frontend."
            )

    log_project_activity(
        project_name,
        "API_CONTRACT_VALIDATED",
        "\n".join(results)
    )

    return f"""
ðŸ”— API CONTRACT REPORT

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
        "Replaced routes.py and api.js with safe /api/items contract."
    )

    return f"""
ðŸ› ï¸ CONTRACT FIX COMPLETE

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
        issues.append("âŒ Missing items table in database.py")
    else:
        issues.append("âœ… items table exists")

    required_columns = ["id", "title", "description"]

    table_match = re.search(
        r"CREATE TABLE IF NOT EXISTS items\s*\((.*?)\)",
        database_code,
        re.DOTALL
    )

    table_definition = ""

    if table_match:
        table_definition = table_match.group(1)

    

    for column in required_columns:

        if column not in table_definition:
            issues.append(
                 f"âŒ Missing column in database.py: {column}"
            )
        else:
            issues.append(
                f"âœ… Column found in database.py: {column}"
            )

    model_requirements = [
        "get_items",
        "add_item",
        "SELECT",
        "INSERT INTO items"
    ]

    for requirement in model_requirements:
        if requirement not in models_code:
            issues.append(f"âŒ Missing in models.py: {requirement}")
        else:
            issues.append(f"âœ… Found in models.py: {requirement}")

    log_project_activity(
        project_name,
        "DATABASE_SCHEMA_VALIDATED",
        "\n".join(issues)
    )

    return f"""
ðŸ—„ DATABASE SCHEMA REPORT

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
ðŸ› ï¸ DATABASE SCHEMA FIX COMPLETE

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

    for attempt in range(retries):
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
        get_project_stack_key(project_name)
    )
    base_url = project_config["backend_url"]
    results = []

    if not wait_for_backend(base_url):
        results.append("âŒ Backend did not start after waiting.")

        return f"""
    ðŸ§ª RUNTIME ENDPOINT TEST

    PROJECT:
    {project_name}

    RESULTS:
    {chr(10).join(results)}
    """

    # Test GET /api/items
    try:
        with urllib.request.urlopen(f"{base_url}/api/items", timeout=5) as response:
            body = response.read().decode("utf-8")
            status = response.status

        if status == 200:
            results.append("âœ… GET /api/items passed")
        else:
            results.append(f"âŒ GET /api/items failed with status {status}")

    except Exception as e:
        results.append(f"âŒ GET /api/items failed: {e}")

    # Test POST /api/items
    try:
        data = json.dumps({
            "title": "Runtime test item",
            "description": "Created by endpoint tester"
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{base_url}/api/items",
            data=data,
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            status = response.status

        if status in [200, 201]:
            results.append("âœ… POST /api/items passed")
        else:
            results.append(f"âŒ POST /api/items failed with status {status}")

    except Exception as e:
        results.append(f"âŒ POST /api/items failed: {e}")

    # Verify insert by reading again
    try:
        with urllib.request.urlopen(f"{base_url}/api/items", timeout=5) as response:
            body = response.read().decode("utf-8")

        if "Runtime test item" in body:
            results.append("âœ… Database insert verified")
        else:
            results.append("âš ï¸ POST succeeded, but inserted item was not found in GET response")

    except Exception as e:
        results.append(f"âŒ Insert verification failed: {e}")

    log_project_activity(
        project_name,
        "RUNTIME_ENDPOINT_TEST",
        "\n".join(results)
    )

    return f"""
ðŸ§ª RUNTIME ENDPOINT TEST

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
        "import backend.models"
    ]

    for bad_import in bad_imports:
        if bad_import in app_code:
            issues.append(f"âŒ Bad backend import found: {bad_import}")

    required_checks = [
        "from flask import Flask",
        "from routes import register_routes",
        "from database import init_db",
        "app = Flask(__name__)",
        "init_db()",
        "register_routes(app)"
    ]

    for check in required_checks:
        if check in app_code:
            issues.append(f"âœ… Found: {check}")
        else:
            issues.append(f"âŒ Missing: {check}")

    if not any(issue.startswith("âŒ") for issue in issues):
        issues.append("âœ… Backend imports look valid.")

    log_project_activity(
        project_name,
        "BACKEND_IMPORTS_VALIDATED",
        "\n".join(issues)
    )

    return f"""
ðŸ“¦ BACKEND IMPORT VALIDATION

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
        "Replaced backend/app.py with safe local imports."
    )

    return f"""
ðŸ› ï¸ BACKEND IMPORT FIX COMPLETE

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
            text=True
        )

        try:
            stdout, stderr = process.communicate(timeout=5)

            combined = (stdout or "") + "\n" + (stderr or "")

            if process.returncode == 0:
                return {
                    "ok": True,
                    "log": combined
                }

            return {
                "ok": False,
                "log": combined
            }

        except subprocess.TimeoutExpired:
            process.kill()

            return {
                "ok": True,
                "log": "Backend started successfully."
            }

    except Exception as e:
        return {
            "ok": False,
            "log": str(e)
        }


def quality_fix_project(project_name):

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
        results.append("Backend smoke test failed. Running fullstack heal...")

        # Store backend error into log-like repair path
        fake_logs = {
            "backend": backend_smoke["log"],
            "frontend": ""
        }

        broken_file = detect_broken_file(backend_smoke["log"])

        if broken_file:
            with open(broken_file, "r", encoding="utf-8") as f:
                broken_code = f.read()

            fixed_code = patch_code(
                broken_code,
                backend_smoke["log"]
            )

            with open(broken_file, "w", encoding="utf-8") as f:
                f.write(fixed_code)

            results.append(f"Healed backend file from smoke test: {broken_file}")

    results.append("STEP 4.6: Clean frontend dependencies")
    results.append(clean_frontend_dependencies(project_name))

    results.append("STEP 5: Run fullstack")
    results.append(run_fullstack_project(project_name))

    results.append("STEP 5.5: Heal fullstack after run")
    results.append(heal_fullstack_project(project_name))

    results.append("STEP 6: Test endpoints")
    endpoint_result = test_runtime_endpoints(project_name)
    results.append(endpoint_result)

    print("ENTER STEP 1")
    print("ENTER STEP 2")
    print("ENTER STEP 3")
    print("ENTER STEP 4")
    print("ENTER STEP 4.5")
    print("ENTER STEP 4.6")
    print("ENTER STEP 5")
    print("ENTER STEP 5.5")
    print("ENTER STEP 6")

    if "âŒ" in endpoint_result:
        final_status = "âŒ NEEDS ATTENTION"
    else:
        final_status = "âœ… READY"

    log_project_activity(
        project_name,
        "QUALITY_FIX_RUN",
        final_status
    )

    return f"""
ðŸ§ª QUALITY FIX REPORT

PROJECT:
{project_name}

FINAL STATUS:
{final_status}

====================
DETAILS
====================
{chr(10).join(results)}
"""

def quality_check_project(project_name):

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

    if "âŒ" in combined:
        final_status = "âŒ NEEDS FIX"
    else:
        final_status = "âœ… READY"

    log_project_activity(
        project_name,
        "QUALITY_CHECK_RUN",
        final_status
    )

    return f"""
ðŸ§ª QUALITY CHECK REPORT

PROJECT:
{project_name}

FINAL STATUS:
{final_status}

====================
DETAILS
====================
{combined}
"""

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
        "@emotion/styled"
    ]

    # Clean package.json
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

    # Clean App.jsx imports/usages
    if os.path.exists(app_file):
        with open(app_file, "r", encoding="utf-8") as f:
            code = f.read()

        for dep in blocked_dependencies:
            if dep in code:
                removed_items.append(f"App.jsx import: {dep}")

        # Remove import lines for blocked deps
        lines = code.splitlines()
        cleaned_lines = []

        for line in lines:
            if any(dep in line for dep in blocked_dependencies):
                continue
            cleaned_lines.append(line)

        code = "\n".join(cleaned_lines)

        # Replace common icon component usage with safe text
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
            "</XMarkIcon>": "</span>"
        }

        for old, new in icon_replacements.items():
            code = code.replace(old, new)

        with open(app_file, "w", encoding="utf-8") as f:
            f.write(code)

    log_project_activity(
        project_name,
        "FRONTEND_DEPENDENCIES_CLEANED",
        f"Removed:\n{chr(10).join(removed_items) if removed_items else 'None'}"
    )

    return f"""
ðŸ§¹ FRONTEND DEPENDENCY CLEAN COMPLETE

PROJECT:
{project_name}

REMOVED:
{chr(10).join(removed_items) if removed_items else "None"}
"""

def modify_app(project_name, change_request):

    project_path = os.path.join(WORKSPACE_DIR, project_name)
    spec_path = os.path.join(project_path, "project_spec.json")

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    if not os.path.exists(spec_path):
        return f"project_spec.json not found for project: {project_name}"

    with open(spec_path, "r", encoding="utf-8") as f:
        current_spec = f.read()

    prompt = f"""
You are a full-stack app modification planner.

Update this project spec based on the requested change.

CURRENT PROJECT SPEC:
{current_spec}

CHANGE REQUEST:
{change_request}

Return ONLY valid JSON.

Rules:
- Keep app_type as React + Flask + SQLite
- Preserve existing features
- Add the requested feature/change
- Update database_tables if needed
- Update api_routes if needed
- Update frontend_pages if needed
- No markdown
- No explanation
"""

    updated_spec_text = clean_code_output(invoke_llm(prompt))

    try:
        updated_spec_json = json.loads(updated_spec_text)

    except Exception:
        current_spec_json = json.loads(current_spec)

        change_lower = change_request.lower()

        for table in current_spec_json.get("database_tables", []):
             if table.get("table_name") == "items":
                fields = table.get("fields", [])

                if "email" in change_lower and "email" not in fields:
                    fields.append("email")

                if "phone" in change_lower and "phone" not in fields:
                    fields.append("phone")

                table["fields"] = fields

        features = current_spec_json.get("features", [])

        if change_request not in features:
            features.append(change_request)

        current_spec_json["features"] = features

        updated_spec_json = current_spec_json

    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(updated_spec_json, f, indent=4)

    log_project_activity(
        project_name,
        "APP_SPEC_MODIFIED",
        f"Change request: {change_request}"
    )

    build_result = build_from_plan(project_name)

    preflight_heal_result = heal_preflight_project(project_name)

    quality_fix_result = quality_fix_project(project_name)

    quality_check_result = quality_check_project(project_name)

    snapshot_result = create_project_snapshot(project_name)

    if "âŒ" in quality_check_result:
        final_status = "âŒ NEEDS ATTENTION"
    else:
        final_status = "âœ… READY"

    log_project_activity(
        project_name,
        "APP_MODIFICATION_COMPLETE",
        f"Change request: {change_request}\nFinal status: {final_status}"
    )

    return f"""
ðŸ› ï¸ APP MODIFICATION COMPLETE

PROJECT:
workspace/{project_name}

CHANGE:
{change_request}

FINAL STATUS:
{final_status}

====================
UPDATED SPEC
====================
{json.dumps(updated_spec_json, indent=4)}

====================
BUILD RESULT
====================
{build_result}

====================
PREFLIGHT HEAL RESULT
====================
{preflight_heal_result}

====================
QUALITY FIX RESULT
====================
{quality_fix_result}

====================
QUALITY CHECK RESULT
====================
{quality_check_result}

====================
SNAPSHOT RESULT
====================
{snapshot_result}
"""

def validate_sqlite_runtime(project_name):

    project_path = os.path.join(WORKSPACE_DIR, project_name)
    backend_path = os.path.join(project_path, "backend")

    database_file = os.path.abspath(
        os.path.join(backend_path, "database.py")
    )

    db_file = os.path.abspath(
        os.path.join(backend_path, "app.db")
    )

    results = []

    if not os.path.exists(database_file):
        return "backend/database.py not found."

    # Step 1: Run database.py/init_db through backend app context
    try:
        old_cwd = os.getcwd()
        os.chdir(backend_path)

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "runtime_database_check",
            database_file
        )

        database_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(database_module)

        if hasattr(database_module, "init_db"):
            database_module.init_db()
            results.append("âœ… init_db() executed successfully")
        else:
            results.append("âŒ init_db() not found in database.py")

        os.chdir(old_cwd)

    except Exception as e:
        try:
            os.chdir(old_cwd)
        except Exception:
            pass

        results.append(f"âŒ init_db() failed: {e}")

    # Step 2: Check actual SQLite DB file
    if not os.path.exists(db_file):
        results.append("âŒ app.db was not created")
    else:
        results.append("âœ… app.db exists")

        try:
            connection = sqlite3.connect(db_file)
            cursor = connection.cursor()

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='items'"
            )

            table = cursor.fetchone()

            if table:
                results.append("âœ… items table exists in app.db")

                cursor.execute("PRAGMA table_info(items)")
                columns = [row[1] for row in cursor.fetchall()]

                required_columns = [
                    "id",
                    "title",
                    "description",
                    "email",
                    "phone"
                ]

                for column in required_columns:
                    if column in columns:
                        results.append(f"âœ… SQLite column exists: {column}")
                    else:
                        results.append(f"âŒ SQLite column missing: {column}")

            else:
                results.append("âŒ items table missing in app.db")

            connection.close()

        except Exception as e:
            results.append(f"âŒ SQLite inspection failed: {e}")

    log_project_activity(
        project_name,
        "SQLITE_RUNTIME_VALIDATED",
        "\n".join(results)
    )

    return f"""
ðŸ—„ SQLITE RUNTIME VALIDATION

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
        "Deleted and recreated app.db using init_db()."
    )

    return f"""
ðŸ› ï¸ SQLITE RUNTIME FIX COMPLETE

PROJECT:
{project_name}

ACTION:
Deleted old app.db and recreated it from database.py.

====================
NEW VALIDATION
====================
{validation_result}
"""

def add_feature(project_name, feature_request):

    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    # Snapshot before changing anything
    before_snapshot = create_project_snapshot(project_name)

    important_files = [
        "backend/app.py",
        "backend/routes.py",
        "backend/database.py",
        "backend/models.py",
        "frontend/src/App.jsx",
        "frontend/src/api.js",
        "frontend/src/style.css",
        "project_spec.json"
    ]

    project_context = []

    for relative_file in important_files:
        file_path = os.path.join(project_path, relative_file)

        if not os.path.exists(file_path):
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        project_context.append(
            f"""
FILE: {relative_file}
CODE:
{content}
"""
        )

    prompt = f"""
You are a careful full-stack code modifier.

Add this feature to the existing project.

PROJECT:
{project_name}

FEATURE REQUEST:
{feature_request}

CURRENT PROJECT FILES:
{chr(10).join(project_context)}

Return ONLY files that must be changed.

STRICT FORMAT:

file: backend/routes.py
<complete updated code>

file: backend/models.py
<complete updated code>

file: frontend/src/App.jsx
<complete updated code>

Rules:
- Do not rebuild the whole project
- Return only changed files
- Each returned file must start with file:
- Use existing architecture
- Backend must use Flask and sqlite3 only
- Frontend must use React, plain CSS, and fetch only
- Do NOT use external UI libraries
- Do NOT use @heroicons/react
- Do NOT use lucide-react
- Do NOT use framer-motion
- Do NOT use Material UI or MUI
- Do NOT use Tailwind CSS
- No markdown
- No explanation
"""

    response = invoke_llm(prompt)

    files_dict = parse_llm_project_output(response)

    if not files_dict:
        return f"""
âŒ FEATURE ADD FAILED

No files were returned by the model.

Snapshot before attempt:
{before_snapshot}
"""

    write_project(project_name, files_dict)

    clean_result = clean_frontend_dependencies(project_name)

    quality_fix_result = quality_fix_project(project_name)

    quality_check_result = quality_check_project(project_name)

    after_snapshot = create_project_snapshot(project_name)

    if "âŒ" in quality_check_result:
        final_status = "âŒ NEEDS ATTENTION"
    else:
        final_status = "âœ… READY"

    log_project_activity(
        project_name,
        "FEATURE_ADDED",
        f"Feature: {feature_request}\nStatus: {final_status}"
    )

    return f"""
âœ¨ FEATURE ADD COMPLETE

PROJECT:
workspace/{project_name}

FEATURE:
{feature_request}

FINAL STATUS:
{final_status}

====================
BEFORE SNAPSHOT
====================
{before_snapshot}

====================
CHANGED FILES
====================
{chr(10).join(files_dict.keys())}

====================
FRONTEND DEP CLEAN
====================
{clean_result}

====================
QUALITY FIX
====================
{quality_fix_result}

====================
QUALITY CHECK
====================
{quality_check_result}

====================
AFTER SNAPSHOT
====================
{after_snapshot}
"""

def add_search_feature(project_name):

    project_path = os.path.join(WORKSPACE_DIR, project_name)
    app_file = os.path.join(project_path, "frontend", "src", "App.jsx")

    if not os.path.exists(app_file):
        return "frontend/src/App.jsx not found."

    create_project_snapshot(project_name)

    search_app_code = """
import { useEffect, useState } from "react";
import { getItems, addItem } from "./api.js";

export default function App() {
    const [items, setItems] = useState([]);
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [email, setEmail] = useState("");
    const [phone, setPhone] = useState("");
    const [search, setSearch] = useState("");

    async function loadItems() {
        const data = await getItems();
        setItems(data);
    }

    async function handleSubmit(event) {
        event.preventDefault();

        if (!title.trim()) {
            return;
        }

        await addItem({
            title,
            description,
            email,
            phone
        });

        setTitle("");
        setDescription("");
        setEmail("");
        setPhone("");

        await loadItems();
    }

    useEffect(() => {
        loadItems();
    }, []);

    const filteredItems = items.filter((item) => {
        const text = `${item.title || ""} ${item.description || ""} ${item.email || ""} ${item.phone || ""}`.toLowerCase();
        return text.includes(search.toLowerCase());
    });

    return (
        <main>
            <h1>Customer Tracker</h1>

            <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search customers"
            />

            <form onSubmit={handleSubmit}>
                <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Name"
                />

                <input
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="Description"
                />

                <input
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="Email"
                />

                <input
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder="Phone"
                />

                <button type="submit">Add</button>
            </form>

            <ul>
                {filteredItems.map((item) => (
                    <li key={item.id}>
                        <strong>{item.title}</strong>
                        <br />
                        {item.description}
                        <br />
                        {item.email}
                        <br />
                        {item.phone}
                    </li>
                ))}
            </ul>
        </main>
    );
}
"""

    with open(app_file, "w", encoding="utf-8") as f:
        f.write(search_app_code)

    clean_frontend_dependencies(project_name)

    quality_fix_result = quality_fix_project(project_name)

    log_project_activity(
        project_name,
        "SEARCH_FEATURE_ADDED",
        "Added frontend search box to App.jsx"
    )

    return f"""
âœ… SEARCH FEATURE ADDED

PROJECT:
{project_name}

UPDATED FILE:
frontend/src/App.jsx

====================
QUALITY FIX
====================
{quality_fix_result}
"""

def run_agent(user_input):
    user_input = user_input.strip()

    if not user_input:
        return AGENT_HELP_TEXT

    user_input_lower = user_input.lower()

    if user_input_lower in ["help", "commands", "what can you do?"]:
        return AGENT_HELP_TEXT

    if user_input_lower in ["supported stacks", "list stacks", "stacks"]:
        return list_supported_stacks()

    if user_input_lower.startswith("plan app "):
        return plan_app(user_input)

    if user_input_lower.startswith("create app "):
        return create_app_workflow(user_input)

    if "create react flask" in user_input_lower or "build react flask" in user_input_lower:
        response = generate_fullstack_project(user_input)

        print("RAW RESPONSE:\n", response)

        files_dict = parse_llm_project_output(response)

        print("PARSED FILES:\n", files_dict)

        project_name = make_safe_project_name(user_input)

        write_project(project_name, files_dict)

        structure_fixes = validate_fullstack_structure(project_name)

        log_project_activity(
            project_name,
            "FULLSTACK_PROJECT_CREATED",
            f"Files:\n{chr(10).join(files_dict.keys())}"
        )

        return f"""
âœ… FULL-STACK PROJECT CREATED SUCCESSFULLY

PROJECT:
workspace/{project_name}

FILES:
{chr(10).join(files_dict.keys())}

STRUCTURE FIXES:
{chr(10).join(structure_fixes)}
"""

    if "create flask" in user_input_lower or "build flask" in user_input_lower:
        response = generate_flask_project(user_input)

        print("RAW RESPONSE:\n", response)

        files_dict = parse_llm_project_output(response)

        print("PARSED FILES:\n", files_dict)

        project_name = make_safe_project_name(user_input)

        write_project(project_name, files_dict)

        structure_fixes = validate_flask_structure(project_name)

        log_project_activity(
            project_name,
            "FLASK_PROJECT_CREATED",
            f"Files:\n{chr(10).join(files_dict.keys())}"
        )

        return f"""
âœ… PROJECT CREATED SUCCESSFULLY

PROJECT:
workspace/{project_name}

FILES:
{chr(10).join(files_dict.keys())}

STRUCTURE FIXES:
{chr(10).join(structure_fixes)}
"""

    if user_input_lower.startswith("heal preflight "):
        project_name = user_input.replace("heal preflight", "").strip()
        return heal_preflight_project(project_name)

    if "heal fullstack" in user_input_lower:
        parts = user_input.split("heal fullstack")

        if len(parts) > 1:
            project_name = parts[1].strip()
            return heal_fullstack_project(project_name)

    if "show logs" in user_input_lower:
        parts = user_input.split("show logs")

        if len(parts) > 1:
            project_name = parts[1].strip()
            return show_fullstack_logs(project_name)

    if "run fullstack" in user_input_lower:
        parts = user_input.split("run fullstack")

        if len(parts) > 1:
            project_name = parts[1].strip()
            return run_fullstack_project(project_name)

    if user_input_lower in ["stop all apps", "stop all fullstack", "stop all projects"]:
        return stop_all_fullstack_projects()

    if "stop fullstack" in user_input_lower:
        parts = user_input.split("stop fullstack")

        if len(parts) > 1:
            project_name = parts[1].strip()
            return stop_fullstack_project(project_name)

    if user_input_lower.startswith("reset database "):
        project_name = strip_command_prefix(user_input, "reset database")
        return reset_project_database(project_name)

    if "run project" in user_input_lower:
        parts = user_input.split("run project")

        if len(parts) > 1:
            project_name = parts[1].strip()
            return self_heal_project(project_name, "app.py")

    if user_input_lower.startswith("snapshot "):
        project_name = user_input.replace("snapshot", "").strip()
        return create_project_snapshot(project_name)

    if user_input_lower.startswith("list snapshots "):
        project_name = user_input.replace("list snapshots", "").strip()
        return list_project_snapshots(project_name)

    if user_input_lower.startswith("restore missing "):
        parts = user_input.split()

        if len(parts) == 3:
            project_name = parts[2]
            return restore_missing_project_files(project_name)

        if len(parts) == 4:
            project_name = parts[2]
            snapshot_name = parts[3]
            return restore_missing_project_files(project_name, snapshot_name)
    
    if user_input_lower.startswith("restore changed "):
        parts = user_input.split()

        if len(parts) == 3:
            project_name = parts[2]
            return restore_changed_project_files(project_name)

        if len(parts) == 4:
            project_name = parts[2]
            snapshot_name = parts[3]
            return restore_changed_project_files(project_name, snapshot_name)


    if user_input_lower.startswith("restore "):
        parts = user_input.split()

        if len(parts) == 2:
            project_name = parts[1]
            return restore_project_snapshot(project_name)

        if len(parts) == 3:
            project_name = parts[1]
            snapshot_name = parts[2]
            return restore_project_snapshot(project_name, snapshot_name)

    if user_input_lower.startswith("review project "):
        project_name = user_input.replace("review project", "").strip()
        return review_project(project_name)

    if user_input_lower.startswith("compare snapshot "):
        parts = user_input.split()

        if len(parts) == 3:
            project_name = parts[2]
            return compare_project_snapshot(project_name)

        if len(parts) == 4:
            project_name = parts[2]
            snapshot_name = parts[3]
            return compare_project_snapshot(project_name, snapshot_name)

    if user_input_lower.startswith("project history "):
        project_name = user_input.replace("project history", "").strip()
        return get_project_history(project_name)

    if user_input_lower.startswith("build from plan "):
        project_name = user_input.replace("build from plan", "").strip()
        return build_from_plan(project_name)

    if user_input_lower.startswith("preflight fullstack "):

        project_name = user_input.replace(
            "preflight fullstack",
            ""
        ).strip()

        return preflight_fullstack_project(
            project_name
        )

    if user_input_lower.startswith("validate contract "):
        project_name = user_input.replace("validate contract", "").strip()
        return validate_api_contract(project_name)

    if user_input_lower.startswith("fix contract "):

        project_name = user_input.replace(
            "fix contract",
            ""
        ).strip()

        return fix_api_contract(project_name)

    if user_input_lower.startswith("validate database "):
        project_name = user_input.replace("validate database", "").strip()
        return validate_database_schema(project_name)

    if user_input_lower.startswith("fix database "):
        project_name = user_input.replace("fix database", "").strip()
        return fix_database_schema(project_name)

    if user_input_lower.startswith("test endpoints "):
        project_name = user_input.replace("test endpoints", "").strip()
        return test_runtime_endpoints(project_name)

    if user_input_lower.startswith("validate imports "):
        project_name = user_input.replace("validate imports", "").strip()
        return validate_backend_imports(project_name)

    if user_input_lower.startswith("fix imports "):
        project_name = user_input.replace("fix imports", "").strip()
        return fix_backend_imports(project_name)

    if user_input_lower.startswith("quality fix "):
        project_name = user_input.replace("quality fix", "").strip()
        return quality_fix_project(project_name)

    if user_input_lower.startswith("quality check "):
        project_name = user_input.replace("quality check", "").strip()
        return quality_check_project(project_name)

    if user_input_lower.startswith("validate app "):
        project_name = strip_command_prefix(user_input, "validate app")
        return validate_generated_app(project_name)

    if user_input_lower.startswith("make standalone "):
        project_name = strip_command_prefix(user_input, "make standalone")
        files = create_standalone_project_files(project_name)
        return f"Standalone files created for {project_name}:\n{chr(10).join(files)}"

    if user_input_lower.startswith("refresh project ports "):
        project_name = strip_command_prefix(user_input, "refresh project ports")
        return refresh_project_ports(project_name)

    if user_input_lower.startswith("refresh project spec "):
        project_name = strip_command_prefix(user_input, "refresh project spec")
        return refresh_project_spec(project_name)

    if user_input_lower.startswith("clean frontend deps "):
        project_name = user_input.replace("clean frontend deps", "").strip()
        return clean_frontend_dependencies(project_name)

    if user_input_lower.startswith("modify app "):
        parts = user_input.split(maxsplit=3)

        if len(parts) < 4:
            return "Use format: modify app <project_name> <change request>"

        project_name = parts[2]
        change_request = parts[3]

        return modify_app(project_name, change_request)

    if user_input_lower.startswith("validate sqlite "):
        project_name = user_input.replace("validate sqlite", "").strip()
        return validate_sqlite_runtime(project_name)

    if user_input_lower.startswith("fix sqlite "):
        project_name = user_input.replace("fix sqlite", "").strip()
        return fix_sqlite_runtime(project_name)

    if user_input_lower.startswith("add feature "):
        parts = user_input.split(maxsplit=3)

        if len(parts) < 4:
            return "Use format: add feature <project_name> <feature request>"

        project_name = parts[2]
        feature_request = parts[3]

        return add_feature(project_name, feature_request)

    if user_input_lower.startswith("add search "):
        project_name = user_input.replace("add search", "").strip()
        return add_search_feature(project_name)

    if looks_like_app_build_request(user_input):
        return create_app_workflow(f"create app {user_input}")

    return f"""Unknown command.

{AGENT_HELP_TEXT}
"""
