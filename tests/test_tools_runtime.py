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


def test_project_dashboard_includes_recent_codegen_and_file_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    project_path = tmp_path / "workspace" / "demo_app"
    (project_path / "backend").mkdir(parents=True)
    (project_path / "frontend" / "src").mkdir(parents=True)
    (project_path / "backend" / "app.py").write_text("print('ok')", encoding="utf-8")
    (project_path / "frontend" / "src" / "App.jsx").write_text("export default function App() {}", encoding="utf-8")
    (project_path / "project_spec.json").write_text(
        json.dumps({"stack_key": "react_flask_sqlite"}),
        encoding="utf-8",
    )
    (project_path / "project_config.json").write_text(
        json.dumps({
            "stack_key": "react_flask_sqlite",
            "frontend_url": "http://127.0.0.1:5173",
            "backend_url": "http://127.0.0.1:5000",
            "frontend_port": 5173,
            "backend_port": 5000,
        }),
        encoding="utf-8",
    )

    sessions_dir = tmp_path / "workspace" / "_runtime" / "codegen_sessions"
    checkpoints_dir = tmp_path / "workspace" / "_runtime" / "codegen_checkpoints"
    sessions_dir.mkdir(parents=True)
    checkpoints_dir.mkdir(parents=True)
    (sessions_dir / "codegen_1.json").write_text(
        json.dumps({
            "id": "codegen_1",
            "project_name": "demo_app",
            "type": "project_save",
            "validation_status": "passed",
            "validation_output": "PASS: all good",
            "checkpoint_id": "checkpoint_1",
            "created_at": "2026-06-28T10:00:00",
            "files": ["demo_app/frontend/src/App.jsx"],
        }),
        encoding="utf-8",
    )
    (checkpoints_dir / "checkpoint_1.json").write_text(
        json.dumps({
            "id": "checkpoint_1",
            "reason": "multi_file_save",
            "created_at": "2026-06-28T10:00:00",
            "files": [
                {
                    "display_path": "demo_app/frontend/src/App.jsx",
                    "relative_path": "demo_app/frontend/src/App.jsx",
                }
            ],
        }),
        encoding="utf-8",
    )

    dashboard = tools.get_project_dashboard("demo_app")

    assert dashboard["exists"] is True
    assert dashboard["file_summary"]["total_files"] >= 4
    assert dashboard["file_summary"]["backend_files"] == 1
    assert dashboard["file_summary"]["frontend_files"] == 1
    assert dashboard["latest_codegen_session"]["id"] == "codegen_1"
    assert dashboard["latest_codegen_checkpoint"]["id"] == "checkpoint_1"
    assert dashboard["latest_validation_status"] == "passed"
    assert "validate app demo_app" in dashboard["quick_commands"]


def test_runtime_health_reports_stale_state_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tools, "find_pids_listening_on_ports", lambda ports: set())

    project_path = tmp_path / "workspace" / "demo_app"
    project_path.mkdir(parents=True)
    (project_path / "project_config.json").write_text(
        json.dumps({
            "stack_key": "react_flask_sqlite",
            "frontend_url": "http://127.0.0.1:5173",
            "backend_url": "http://127.0.0.1:5000",
            "frontend_port": 5173,
            "backend_port": 5000,
        }),
        encoding="utf-8",
    )
    state_dir = tmp_path / "workspace" / "_runtime"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
        json.dumps({
            "demo_app": {
                "backend_pid": 111,
                "frontend_pid": 222,
            }
        }),
        encoding="utf-8",
    )

    health = tools.get_project_runtime_health("demo_app")
    report = tools.format_runtime_health_report("demo_app")
    cleanup = tools.cleanup_stale_runtime_state("demo_app")

    assert health["status"] == "stale"
    assert health["stale_runtime_state"] is True
    assert "cleanup runtime demo_app" in report
    assert "Cleared stale runtime state" in cleanup
    assert tools.get_project_runtime_state("demo_app") == {}


def test_runtime_cleanup_skips_when_ports_are_active(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tools, "find_pids_listening_on_ports", lambda ports: {999})

    project_path = tmp_path / "workspace" / "demo_app"
    project_path.mkdir(parents=True)
    (project_path / "project_config.json").write_text(
        json.dumps({
            "stack_key": "react_flask_sqlite",
            "frontend_url": "http://127.0.0.1:5173",
            "backend_url": "http://127.0.0.1:5000",
            "frontend_port": 5173,
            "backend_port": 5000,
        }),
        encoding="utf-8",
    )

    output = tools.cleanup_stale_runtime_state("demo_app")

    assert "RUNTIME CLEANUP SKIPPED" in output
    assert "999" in output
