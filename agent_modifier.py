import json
import os

from agent_llm import invoke_llm
from agent_project_files import parse_llm_project_output, write_project
from agent_text import clean_code_output
from tools import create_project_snapshot, log_project_activity


WORKSPACE_DIR = "workspace"


def modify_app(
    project_name,
    change_request,
    build_from_plan,
    heal_preflight_project,
    quality_fix_project,
    quality_check_project,
):
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
        f"Change request: {change_request}",
    )

    build_result = build_from_plan(project_name)
    preflight_heal_result = heal_preflight_project(project_name)
    quality_fix_result = quality_fix_project(project_name)
    quality_check_result = quality_check_project(project_name)
    snapshot_result = create_project_snapshot(project_name)

    if "NEEDS FIX" in quality_check_result or "FAIL:" in quality_check_result or "âŒ" in quality_check_result:
        final_status = "NEEDS ATTENTION"
    else:
        final_status = "READY"

    log_project_activity(
        project_name,
        "APP_MODIFICATION_COMPLETE",
        f"Change request: {change_request}\nFinal status: {final_status}",
    )

    return f"""
APP MODIFICATION COMPLETE

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


def add_feature(
    project_name,
    feature_request,
    clean_frontend_dependencies,
    quality_fix_project,
    quality_check_project,
):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    before_snapshot = create_project_snapshot(project_name)

    important_files = [
        "backend/app.py",
        "backend/routes.py",
        "backend/database.py",
        "backend/models.py",
        "frontend/src/App.jsx",
        "frontend/src/api.js",
        "frontend/src/style.css",
        "project_spec.json",
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
FEATURE ADD FAILED

No files were returned by the model.

Snapshot before attempt:
{before_snapshot}
"""

    write_project(project_name, files_dict)

    clean_result = clean_frontend_dependencies(project_name)
    quality_fix_result = quality_fix_project(project_name)
    quality_check_result = quality_check_project(project_name)
    after_snapshot = create_project_snapshot(project_name)

    if "NEEDS FIX" in quality_check_result or "FAIL:" in quality_check_result or "âŒ" in quality_check_result:
        final_status = "NEEDS ATTENTION"
    else:
        final_status = "READY"

    log_project_activity(
        project_name,
        "FEATURE_ADDED",
        f"Feature: {feature_request}\nStatus: {final_status}",
    )

    return f"""
FEATURE ADD COMPLETE

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


def add_search_feature(project_name, clean_frontend_dependencies, quality_fix_project):
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
        "Added frontend search box to App.jsx",
    )

    return f"""
SEARCH FEATURE ADDED

PROJECT:
{project_name}

UPDATED FILE:
frontend/src/App.jsx

====================
QUALITY FIX
====================
{quality_fix_result}
"""
