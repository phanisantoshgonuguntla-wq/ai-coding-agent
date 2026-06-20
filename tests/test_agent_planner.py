import json

import agent_planner


def test_create_fallback_project_spec_detects_domain_entity():
    spec = agent_planner.create_fallback_project_spec(
        "inventory_app",
        "build inventory management for products with quantity and price",
        "react_flask_sqlite",
    )

    assert spec["resource_name"] == "products"
    assert spec["primary_entity"] == "product"
    assert "quantity" in spec["entities"][0]["fields"]
    assert "price" in spec["entities"][0]["fields"]


def test_normalize_project_spec_creates_stack_config_in_temp_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    spec = agent_planner.normalize_project_spec(
        "inventory_app",
        "inventory app for products",
        {"description": "Generated app plan fallback because model returned invalid JSON."},
        "react_flask_sqlite",
    )

    assert spec["app_name"] == "inventory_app"
    assert spec["stack_key"] == "react_flask_sqlite"
    assert spec["resource_name"] == "products"
    assert spec["run_urls"]["frontend"] == "http://127.0.0.1:5173"
    assert spec["run_urls"]["backend"] == "http://127.0.0.1:5000"

    config_path = tmp_path / "workspace" / "inventory_app" / "project_config.json"
    assert config_path.exists()
    assert json.loads(config_path.read_text())["frontend_port"] == 5173


def test_normalize_project_spec_rejects_invalid_route_shape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    spec = agent_planner.normalize_project_spec(
        "tasks_app",
        "task tracker",
        {
            "api_routes": [
                {"route_name": "/api/items", "method": "GET"},
            ]
        },
        "react_flask_sqlite",
    )

    methods = {route["method"] for route in spec["api_routes"]}
    assert {"GET", "POST"}.issubset(methods)
