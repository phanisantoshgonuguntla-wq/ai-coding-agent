import json
import os

from agent_llm import invoke_llm
from agent_stacks import (
    SUPPORTED_APP_STACKS,
    detect_requested_stack,
    get_project_stack_key,
    get_stack,
    get_stack_build_steps,
)
from agent_text import clean_code_output, make_safe_project_name, strip_command_prefix
from tools import ensure_project_config, log_project_activity


WORKSPACE_DIR = "workspace"


def singularize_entity_name(name):
    name = name.strip().lower()

    if name.endswith("ies"):
        return name[:-3] + "y"

    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]

    return name or "record"


def detect_domain_entity(requirement):
    text = requirement.lower()

    domain_candidates = [
        ("customer", "customers"),
        ("crm", "customers"),
        ("client", "customers"),
        ("note", "notes"),
        ("task", "tasks"),
        ("todo", "tasks"),
        ("lead", "leads"),
        ("sales", "leads"),
        ("inventory", "products"),
        ("product", "products"),
        ("order", "orders"),
        ("employee", "employees"),
        ("student", "students"),
        ("expense", "expenses"),
        ("invoice", "invoices"),
    ]

    for keyword, entity_name in domain_candidates:
        if keyword in text:
            return entity_name

    return "records"


def detect_entity_fields(requirement, entity_name):
    text = requirement.lower()
    fields = ["id"]

    if entity_name == "customers":
        fields.extend(["name", "email", "phone", "notes"])
    elif entity_name == "notes":
        fields.extend(["title", "description"])
    elif entity_name == "tasks":
        fields.extend(["title", "description", "status"])
    elif entity_name == "leads":
        fields.extend(["name", "email", "phone", "status", "notes"])
    elif entity_name == "products":
        fields.extend(["name", "description", "quantity", "price"])
    else:
        fields.extend(["title", "description"])

    optional_field_keywords = {
        "name": ["name"],
        "email": ["email"],
        "phone": ["phone"],
        "notes": ["note", "notes"],
        "description": ["description", "details"],
        "status": ["status"],
        "due_date": ["due date", "deadline"],
        "priority": ["priority"],
        "price": ["price", "cost"],
        "quantity": ["quantity", "stock"],
        "category": ["category"],
    }

    for field_name, keywords in optional_field_keywords.items():
        if entity_name == "notes" and field_name == "notes":
            continue

        if any(keyword in text for keyword in keywords) and field_name not in fields:
            fields.append(field_name)

    return fields


def create_fallback_project_spec(project_name, requirement, stack_key):
    stack = get_stack(stack_key)
    entity_name = detect_domain_entity(requirement or project_name)
    singular_name = singularize_entity_name(entity_name)
    fields = detect_entity_fields(requirement or project_name, entity_name)
    display_name = project_name.replace("_", " ").title()

    return {
        "app_name": project_name,
        "display_name": display_name,
        "stack_key": stack_key,
        "app_type": stack["label"],
        "description": f"A {stack['label']} application for managing {entity_name}.",
        "resource_name": entity_name,
        "primary_entity": singular_name,
        "entities": [
            {
                "name": entity_name,
                "singular_name": singular_name,
                "fields": fields,
                "required_fields": [
                    field
                    for field in fields
                    if field in ["name", "title"]
                ],
                "searchable_fields": [
                    field
                    for field in fields
                    if field not in ["id", "price", "quantity"]
                ],
            }
        ],
        "features": [
            f"Create {entity_name}",
            f"List {entity_name}",
            f"Persist {entity_name} in SQLite",
            f"Validate required {singular_name} fields",
            f"Search {entity_name}",
        ],
        "database_tables": [
            {
                "table_name": "items",
                "entity": entity_name,
                "fields": fields,
            }
        ],
        "api_base_path": "/api/items",
        "api_routes": [
            {
                "route_name": "/api/items",
                "method": "GET",
                "purpose": f"List {entity_name}",
            },
            {
                "route_name": "/api/items",
                "method": "POST",
                "purpose": f"Create a {singular_name}",
            },
        ],
        "frontend_pages": [
            {
                "name": "Dashboard",
                "purpose": f"Manage {entity_name}",
            }
        ],
        "validation_rules": [
            "Frontend package must build successfully",
            "Backend GET /api/items must return JSON",
            "Backend POST /api/items must persist a record",
            "Frontend api.js must call the assigned backend URL",
            "Inserted data must remain after backend restart",
        ],
        "build_steps": get_stack_build_steps(stack_key),
        "test_plan": [
            "Run validate app after build",
            "Create a sample record from the frontend",
            "Refresh the frontend and confirm data remains",
            "Restart fullstack app and confirm persistence",
        ],
    }


def is_fallback_description(description):
    return "fallback because model returned invalid json" in str(description).lower()


def is_string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def normalize_api_routes(value, fallback_routes):
    if not isinstance(value, list):
        return fallback_routes

    routes = []

    for route in value:
        if not isinstance(route, dict):
            continue

        route_name = route.get("route_name") or route.get("route_path") or route.get("path")
        method = str(route.get("method", "")).upper()

        if not route_name or method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            continue

        routes.append({
            "route_name": route_name,
            "method": method,
            "purpose": route.get("purpose", ""),
        })

    expected_methods = {
        route["method"]
        for route in routes
        if route.get("route_name") == "/api/items"
    }

    if not {"GET", "POST"}.issubset(expected_methods):
        return fallback_routes

    return routes


def normalize_frontend_pages(value, fallback_pages):
    if not isinstance(value, list):
        return fallback_pages

    pages = []

    for page in value:
        if isinstance(page, str):
            pages.append({
                "name": page,
                "purpose": "",
            })
        elif isinstance(page, dict):
            name = page.get("name") or page.get("page_name")

            if name:
                if any(term in name.lower() for term in ["login", "register", "registration"]):
                    return fallback_pages

                pages.append({
                    "name": name,
                    "purpose": page.get("purpose", ""),
                })

    return pages or fallback_pages


def normalize_project_spec(project_name, requirement, spec_json, stack_key):
    fallback_spec = create_fallback_project_spec(project_name, requirement, stack_key)

    if not isinstance(spec_json, dict):
        spec_json = {}

    normalized = dict(fallback_spec)
    normalized.update({
        key: value
        for key, value in spec_json.items()
        if value not in [None, "", [], {}]
    })

    if normalized.get("stack_key") not in SUPPORTED_APP_STACKS:
        normalized["stack_key"] = stack_key

    normalized["app_name"] = project_name
    normalized["app_type"] = get_stack(normalized["stack_key"])["label"]

    if is_fallback_description(normalized.get("description")):
        normalized["description"] = fallback_spec["description"]

    if (
        normalized.get("resource_name") == "records"
        and fallback_spec["resource_name"] != "records"
    ):
        normalized["resource_name"] = fallback_spec["resource_name"]
        normalized["primary_entity"] = fallback_spec["primary_entity"]

        if (
            normalized.get("entities")
            and isinstance(normalized["entities"][0], dict)
            and normalized["entities"][0].get("name") == "records"
        ):
            normalized["entities"] = fallback_spec["entities"]

    if not normalized.get("entities"):
        normalized["entities"] = fallback_spec["entities"]

    if not normalized.get("database_tables"):
        normalized["database_tables"] = fallback_spec["database_tables"]

    normalized["resource_name"] = normalized.get("resource_name") or fallback_spec["resource_name"]
    normalized["primary_entity"] = normalized.get("primary_entity") or fallback_spec["primary_entity"]
    features = normalized.get("features")
    has_generic_record_features = (
        normalized.get("resource_name") != "records"
        and is_string_list(features)
        and any("record" in feature.lower() for feature in features)
    )
    normalized["features"] = (
        features
        if is_string_list(features) and not has_generic_record_features
        else fallback_spec["features"]
    )
    normalized["validation_rules"] = (
        normalized["validation_rules"]
        if is_string_list(normalized.get("validation_rules"))
        else fallback_spec["validation_rules"]
    )
    normalized["test_plan"] = (
        normalized["test_plan"]
        if is_string_list(normalized.get("test_plan"))
        else fallback_spec["test_plan"]
    )
    normalized["api_base_path"] = "/api/items"
    normalized["api_routes"] = normalize_api_routes(
        normalized.get("api_routes"),
        fallback_spec["api_routes"],
    )
    normalized["frontend_pages"] = normalize_frontend_pages(
        normalized.get("frontend_pages"),
        fallback_spec["frontend_pages"],
    )
    normalized["build_steps"] = get_stack_build_steps(normalized["stack_key"])

    project_config = ensure_project_config(project_name, normalized["stack_key"])
    normalized["run_urls"] = {
        "frontend": project_config["frontend_url"],
        "backend": project_config["backend_url"],
    }
    normalized["ports"] = {
        "frontend": project_config["frontend_port"],
        "backend": project_config["backend_port"],
    }

    return normalized


def refresh_project_spec(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    spec_path = os.path.join(project_path, "project_spec.json")

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    stack_key = get_project_stack_key(project_name)

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            existing_spec = json.load(f)
    except Exception:
        existing_spec = {}

    description = existing_spec.get("description", "")
    requirement = project_name if is_fallback_description(description) else description or project_name
    normalized_spec = normalize_project_spec(
        project_name,
        requirement,
        existing_spec,
        stack_key,
    )

    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(normalized_spec, f, indent=4)

    log_project_activity(
        project_name,
        "PROJECT_SPEC_REFRESHED",
        "Normalized project_spec.json with stack-aware schema.",
    )

    return f"""
PROJECT SPEC REFRESHED

PROJECT:
{project_name}

SPEC FILE:
project_spec.json

STACK:
{normalized_spec["app_type"]}

RESOURCE:
{normalized_spec["resource_name"]}

RUN URLS:
Frontend: {normalized_spec["run_urls"]["frontend"]}
Backend: {normalized_spec["run_urls"]["backend"]}
"""


def create_app_plan(user_input, stack_key=None):
    stack_key = stack_key or detect_requested_stack(user_input)
    stack = get_stack(stack_key)

    prompt = f"""
You are a senior software architect.

Convert this app requirement into a clear build plan.

USER REQUIREMENT:
{user_input}

TARGET STACK:
{stack["label"]}

Return ONLY valid JSON.

JSON format:
{{
  "app_name": "",
  "display_name": "",
  "stack_key": "{stack_key}",
  "app_type": "{stack["label"]}",
  "description": "",
  "resource_name": "",
  "primary_entity": "",
  "entities": [
    {{
      "name": "",
      "singular_name": "",
      "fields": [],
      "required_fields": [],
      "searchable_fields": []
    }}
  ],
  "features": [],
  "database_tables": [],
  "api_base_path": "/api/items",
  "api_routes": [],
  "frontend_pages": [],
  "validation_rules": [],
  "build_steps": [],
  "test_plan": [],
  "run_urls": {{}},
  "ports": {{}}
}}

Rules:
- No markdown
- No explanation
- JSON only
- app_type must be exactly "{stack["label"]}"
- stack_key must be exactly "{stack_key}"
"""

    response = invoke_llm(prompt)
    return clean_code_output(response)


def save_project_spec(project_name, spec_text, stack_key="react_flask_sqlite", requirement=""):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    os.makedirs(project_path, exist_ok=True)

    spec_path = os.path.join(project_path, "project_spec.json")

    try:
        spec_json = json.loads(spec_text)
    except Exception:
        spec_json = {}

    spec_json = normalize_project_spec(
        project_name,
        requirement or project_name,
        spec_json,
        stack_key,
    )

    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec_json, f, indent=4)

    return spec_path


def plan_app(user_input):
    stack_key = detect_requested_stack(user_input)
    plan_text = create_app_plan(user_input, stack_key)

    requirement = strip_command_prefix(user_input, "plan app")
    project_name = make_safe_project_name(requirement)

    spec_path = save_project_spec(project_name, plan_text, stack_key, requirement)

    with open(spec_path, "r", encoding="utf-8") as f:
        clean_plan = f.read()

    log_project_activity(
        project_name,
        "APP_PLAN_CREATED",
        f"Spec saved to: {spec_path}",
    )

    return f"""
APP PLAN CREATED

PROJECT:
workspace/{project_name}

SPEC FILE:
project_spec.json

PLAN:
{clean_plan}
"""
