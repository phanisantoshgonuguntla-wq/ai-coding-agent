import json
from types import SimpleNamespace

import tools


def test_runtime_state_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = {
        "stack_key": "react_flask_sqlite",
        "frontend_url": "http://127.0.0.1:5173",
        "backend_url": "http://127.0.0.1:5000",
        "frontend_port": 5173,
        "backend_port": 5000,
    }
    processes = {
        "backend": SimpleNamespace(pid=111),
        "frontend": SimpleNamespace(pid=222),
    }

    runtime_state = tools.save_project_runtime_state("demo_app", config, processes)

    assert runtime_state["backend_pid"] == 111
    assert runtime_state["frontend_pid"] == 222
    assert runtime_state["log_files"]["backend"].endswith("demo_app_backend.log")

    state_path = tmp_path / "workspace" / "_runtime" / "state.json"
    assert state_path.exists()
    assert json.loads(state_path.read_text())["demo_app"]["frontend_port"] == 5173

    assert tools.get_runtime_state_pids("demo_app") == [111, 222]

    tools.clear_project_runtime_state("demo_app")

    assert tools.get_project_runtime_state("demo_app") == {}


def test_get_fullstack_logs_falls_back_to_runtime_log_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = {
        "stack_key": "react_flask_sqlite",
        "frontend_url": "http://127.0.0.1:5173",
        "backend_url": "http://127.0.0.1:5000",
        "frontend_port": 5173,
        "backend_port": 5000,
    }
    processes = {
        "backend": SimpleNamespace(pid=111),
        "frontend": SimpleNamespace(pid=222),
    }

    runtime_state = tools.save_project_runtime_state("demo_app", config, processes)
    backend_log = runtime_state["log_files"]["backend"]
    frontend_log = runtime_state["log_files"]["frontend"]

    with open(backend_log, "w", encoding="utf-8") as f:
        f.write("backend ready")

    with open(frontend_log, "w", encoding="utf-8") as f:
        f.write("frontend ready")

    tools.FULLSTACK_LOGS.clear()

    logs = tools.get_fullstack_logs("demo_app")

    assert logs["backend"] == "backend ready"
    assert logs["frontend"] == "frontend ready"


def test_show_fullstack_logs_reports_persisted_log_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = {
        "stack_key": "react_flask_sqlite",
        "frontend_url": "http://127.0.0.1:5173",
        "backend_url": "http://127.0.0.1:5000",
        "frontend_port": 5173,
        "backend_port": 5000,
    }
    processes = {
        "backend": SimpleNamespace(pid=111),
        "frontend": SimpleNamespace(pid=222),
    }

    tools.save_project_runtime_state("demo_app", config, processes)
    output = tools.show_fullstack_logs("demo_app")

    assert "===== LOG FILES =====" in output
    assert "demo_app_backend.log" in output
    assert "demo_app_frontend.log" in output
