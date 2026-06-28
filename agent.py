import os
import re
import json
import time
import subprocess
import sys
import sqlite3

import agent_builder
import agent_codegen
import agent_healer
import agent_llm
import agent_commands
import agent_modifier
import agent_quality
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
    detect_requested_stack,
    get_project_stack_key,
    get_stack,
    list_supported_stacks,
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
    reset_project_database,
    run_frontend_build,
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

- generate code <prompt>
  Generate standalone code from a prompt without writing files.

- generate code file <workspace_path> <prompt>
  Generate standalone code and save it under workspace/.

- preview code file <workspace_path> <prompt>
  Preview generated code, target path, and overwrite/create status without writing files.

- save code file <workspace_path> <prompt>
  Generate standalone code and save it under workspace/.

- preview code files <prompt>
  Preview multiple generated files, including create/overwrite status and diffs.

- save code files <prompt>
  Generate and save multiple files under workspace/.

- preview project code <project_name> <prompt>
  Preview project-aware generated changes using workspace/<project_name> context.

- save project code <project_name> <prompt>
  Generate and save project-aware changes under workspace/<project_name>.

- explain project context <project_name> <prompt>
  Show which project files would be included as context for a prompt.

- list codegen sessions
  Show recent project-aware code generation sessions.

- show codegen session <session_id>
  Show details for a saved code generation session.

- list codegen checkpoints
  Show recent generated-code save checkpoints.

- show codegen checkpoint <checkpoint_id>
  Show files that a checkpoint can restore or delete.

- restore codegen checkpoint <checkpoint_id>
  Restore workspace files from a generated-code save checkpoint.

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

def self_heal_project(project_name, entry_file):
    return agent_healer.self_heal_project(
        project_name,
        entry_file,
        validate_flask_structure,
        patch_code,
    )


def detect_frontend_broken_file(frontend_logs, project_name):
    return agent_healer.detect_frontend_broken_file(frontend_logs, project_name)


def patch_frontend_code(original_code, error_logs, file_name):
    return agent_healer.patch_frontend_code(original_code, error_logs, file_name)


def heal_fullstack_project(project_name):
    return agent_healer.heal_fullstack_project(project_name, patch_code)


def heal_preflight_project(project_name):
    return agent_healer.heal_preflight_project(project_name, patch_code)


def validate_api_contract(project_name):
    return agent_quality.validate_api_contract(project_name)


def fix_api_contract(project_name):
    return agent_quality.fix_api_contract(project_name)


def validate_database_schema(project_name):
    return agent_quality.validate_database_schema(project_name)


def fix_database_schema(project_name):
    return agent_quality.fix_database_schema(project_name)


def test_runtime_endpoints(project_name):
    return agent_quality.test_runtime_endpoints(project_name)


def validate_backend_imports(project_name):
    return agent_quality.validate_backend_imports(project_name)


def fix_backend_imports(project_name):
    return agent_quality.fix_backend_imports(project_name)


def smoke_test_backend(project_name):
    return agent_quality.smoke_test_backend(project_name)


def clean_frontend_dependencies(project_name):
    return agent_quality.clean_frontend_dependencies(project_name)


def validate_sqlite_runtime(project_name):
    return agent_quality.validate_sqlite_runtime(project_name)


def validate_frontend_build(project_name):
    ok, detail = run_frontend_build(project_name)
    status = "PASS" if ok else "FAIL"

    return f"""FRONTEND BUILD VALIDATION

PROJECT:
{project_name}

RESULT:
{status}: {detail}
"""


def fix_sqlite_runtime(project_name):
    return agent_quality.fix_sqlite_runtime(project_name)


def quality_fix_project(project_name):
    return agent_quality.quality_fix_project(
        project_name,
        patch_code,
        basic_project_quality_check,
    )


def quality_check_project(project_name):
    return agent_quality.quality_check_project(
        project_name,
        basic_project_quality_check,
    )


def modify_app(project_name, change_request):
    return agent_modifier.modify_app(
        project_name,
        change_request,
        build_from_plan,
        heal_preflight_project,
        quality_fix_project,
        quality_check_project,
    )


def add_feature(project_name, feature_request):
    return agent_modifier.add_feature(
        project_name,
        feature_request,
        clean_frontend_dependencies,
        quality_fix_project,
        quality_check_project,
    )


def add_search_feature(project_name):
    return agent_modifier.add_search_feature(
        project_name,
        clean_frontend_dependencies,
        quality_fix_project,
    )


def generate_code(prompt):
    return agent_codegen.generate_code(prompt)


def preview_generated_code_file(file_path, prompt):
    return agent_codegen.preview_generated_code(file_path, prompt, WORKSPACE_DIR)


def build_generated_code_preview(file_path, prompt):
    return agent_codegen.build_generated_code_preview(file_path, prompt, WORKSPACE_DIR)


def build_generated_code_files_preview(prompt):
    return agent_codegen.build_generated_code_files_preview(prompt, WORKSPACE_DIR)


def build_project_code_files_preview(project_name, prompt):
    return agent_codegen.build_project_code_files_preview(project_name, prompt, WORKSPACE_DIR)


def build_project_repair_files_preview(project_name, prompt, validation_output):
    return agent_codegen.build_project_repair_files_preview(
        project_name,
        prompt,
        validation_output,
        WORKSPACE_DIR,
    )


def save_code_content(file_path, code):
    return agent_codegen.save_code_content(file_path, code, WORKSPACE_DIR)


def save_code_files_content(files):
    return agent_codegen.save_code_files_content(files, WORKSPACE_DIR)


def save_generated_code(file_path, prompt):
    return agent_codegen.save_generated_code(file_path, prompt, WORKSPACE_DIR)


def preview_generated_code_files(prompt):
    return agent_codegen.preview_generated_code_files(prompt, WORKSPACE_DIR)


def save_generated_code_files(prompt):
    return agent_codegen.save_generated_code_files(prompt, WORKSPACE_DIR)


def preview_project_code_files(project_name, prompt):
    return agent_codegen.preview_project_code_files(project_name, prompt, WORKSPACE_DIR)


def save_generated_project_code_files(project_name, prompt):
    return agent_codegen.save_generated_project_code_files(project_name, prompt, WORKSPACE_DIR)


def preview_project_repair_files(project_name, prompt, validation_output):
    return agent_codegen.preview_project_repair_files(
        project_name,
        prompt,
        validation_output,
        WORKSPACE_DIR,
    )


def explain_project_context(project_name, prompt):
    return agent_codegen.explain_project_context(project_name, prompt, WORKSPACE_DIR)


def record_codegen_session(
    session_type,
    project_name,
    prompt,
    files,
    validation_output="",
    dependency_warnings=None,
    checkpoint_id="",
    git_summary="",
    implementation_plan="",
):
    return agent_codegen.record_codegen_session(
        session_type,
        project_name,
        prompt,
        files,
        validation_output,
        dependency_warnings,
        checkpoint_id,
        git_summary,
        implementation_plan,
        WORKSPACE_DIR,
    )


def list_codegen_sessions():
    return agent_codegen.list_codegen_sessions(WORKSPACE_DIR)


def get_codegen_session_records(limit=20):
    return agent_codegen.get_codegen_session_records(WORKSPACE_DIR, limit)


def show_codegen_session(session_id):
    return agent_codegen.show_codegen_session(session_id, WORKSPACE_DIR)


def list_codegen_checkpoints():
    return agent_codegen.list_codegen_checkpoints(WORKSPACE_DIR)


def show_codegen_checkpoint(checkpoint_id):
    return agent_codegen.show_codegen_checkpoint(checkpoint_id, WORKSPACE_DIR)


def restore_codegen_checkpoint(checkpoint_id):
    return agent_codegen.restore_codegen_checkpoint(checkpoint_id, WORKSPACE_DIR)


def validate_codegen_changes(project_name, files):
    stack_key = get_project_stack_key(project_name)
    validators = {
        "backend_imports": validate_backend_imports,
        "database_schema": validate_database_schema,
        "sqlite_runtime": validate_sqlite_runtime,
        "api_contract": validate_api_contract,
        "frontend_build": validate_frontend_build,
        "full_app_validation": validate_generated_app,
    }

    return agent_codegen.validate_codegen_changes(
        project_name,
        files,
        stack_key,
        validators,
    )


def extract_codegen_checkpoint_id(output):
    return agent_codegen.extract_codegen_checkpoint_id(output)


def build_codegen_git_summary(files, prompt):
    return agent_codegen.build_codegen_git_summary(files, prompt)


def run_agent(user_input):
    return agent_commands.run_agent(user_input, globals())
