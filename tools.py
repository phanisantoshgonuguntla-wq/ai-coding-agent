FULLSTACK_PROCESSES = {}
FULLSTACK_LOGS = {}

import os
import re
import sys
import time
import subprocess
import threading
import shutil
import filecmp
import ast
import json
import urllib.request
import urllib.error
from datetime import datetime

WORKSPACE_DIR = "workspace"
RUNTIME_DIR = os.path.join(WORKSPACE_DIR, "_runtime")
RUNTIME_STATE_FILE = os.path.join(RUNTIME_DIR, "state.json")
RUNTIME_LOG_DIR = os.path.join(RUNTIME_DIR, "logs")


def ensure_runtime_dirs():
    os.makedirs(RUNTIME_LOG_DIR, exist_ok=True)


def read_runtime_state():
    if not os.path.exists(RUNTIME_STATE_FILE):
        return {}

    try:
        with open(RUNTIME_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_runtime_state(state):
    ensure_runtime_dirs()

    with open(RUNTIME_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)


def get_project_runtime_state(project_name):
    return read_runtime_state().get(project_name, {})


def get_runtime_log_paths(project_name):
    ensure_runtime_dirs()
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", project_name)

    return {
        "backend": os.path.join(RUNTIME_LOG_DIR, f"{safe_name}_backend.log"),
        "frontend": os.path.join(RUNTIME_LOG_DIR, f"{safe_name}_frontend.log")
    }


def read_runtime_log_file(path):
    if not path or not os.path.exists(path):
        return ""

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def save_project_runtime_state(project_name, config, processes):
    state = read_runtime_state()
    log_paths = get_runtime_log_paths(project_name)

    state[project_name] = {
        "project_name": project_name,
        "stack_key": config.get("stack_key"),
        "frontend_url": config.get("frontend_url"),
        "backend_url": config.get("backend_url"),
        "frontend_port": config.get("frontend_port"),
        "backend_port": config.get("backend_port"),
        "backend_pid": processes["backend"].pid,
        "frontend_pid": processes["frontend"].pid,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "log_files": log_paths,
    }

    write_runtime_state(state)
    return state[project_name]


def clear_project_runtime_state(project_name):
    state = read_runtime_state()

    if project_name in state:
        del state[project_name]
        write_runtime_state(state)


def get_runtime_state_pids(project_name):
    runtime_state = get_project_runtime_state(project_name)
    pids = []

    for key in ["backend_pid", "frontend_pid"]:
        pid = runtime_state.get(key)

        if isinstance(pid, int):
            pids.append(pid)

    return pids


def get_project_spec(project_name):
    spec_path = os.path.join(WORKSPACE_DIR, project_name, "project_spec.json")

    if not os.path.exists(spec_path):
        return {}

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_project_stack_key(project_name):
    spec = get_project_spec(project_name)
    return spec.get("stack_key", "react_flask_sqlite")


def get_default_backend_port(stack_key):
    if stack_key == "react_php_sqlite":
        return 8000

    return 5000


def get_required_files_for_stack(stack_key):
    common_frontend = [
        "frontend/package.json",
        "frontend/index.html",
        "frontend/src/main.jsx",
        "frontend/src/App.jsx",
        "frontend/src/api.js",
        "frontend/src/style.css"
    ]

    if stack_key == "react_dotnet_sqlite":
        return [
            "backend/GeneratedApp.Api.csproj",
            "backend/Program.cs",
            *common_frontend
        ]

    if stack_key == "react_php_sqlite":
        return [
            "backend/index.php",
            "backend/database.php",
            *common_frontend
        ]

    return [
        "backend/app.py",
        "backend/routes.py",
        "backend/database.py",
        "backend/models.py",
        "backend/requirements.txt",
        *common_frontend
    ]


def get_existing_project_ports(exclude_project=None):
    used_ports = set()

    if not os.path.exists(WORKSPACE_DIR):
        return used_ports

    for project_name in os.listdir(WORKSPACE_DIR):
        if project_name.startswith("_") or project_name == exclude_project:
            continue

        config_path = os.path.join(WORKSPACE_DIR, project_name, "project_config.json")

        if not os.path.exists(config_path):
            continue

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            for key in ["frontend_port", "backend_port"]:
                port = config.get(key)

                if isinstance(port, int):
                    used_ports.add(port)
        except Exception:
            continue

    return used_ports


def list_workspace_projects():
    if not os.path.exists(WORKSPACE_DIR):
        return []

    return sorted(
        name
        for name in os.listdir(WORKSPACE_DIR)
        if os.path.isdir(os.path.join(WORKSPACE_DIR, name))
        and not name.startswith("_")
    )


def get_project_config(project_name, create_if_missing=True):
    config_path = os.path.join(WORKSPACE_DIR, project_name, "project_config.json")

    if not os.path.exists(config_path):
        if not create_if_missing:
            return None
        return ensure_project_config(project_name)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        if not create_if_missing:
            return None
        return ensure_project_config(project_name)


def find_pids_listening_on_ports(ports):
    wanted_ports = {int(port) for port in ports if port}
    pids = set()

    if not wanted_ports:
        return pids

    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            timeout=15
        )
    except Exception:
        return pids

    for line in result.stdout.splitlines():
        if "LISTENING" not in line:
            continue

        parts = line.split()

        if len(parts) < 5:
            continue

        local_address = parts[1]
        pid = parts[-1]
        match = re.search(r":(\d+)$", local_address)

        if not match:
            continue

        port = int(match.group(1))

        if port in wanted_ports and pid.isdigit():
            pids.add(int(pid))

    return pids


def is_port_listening(port):
    if not port:
        return False

    return bool(find_pids_listening_on_ports([port]))


def taskkill_process_tree(pid):
    result = subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return f"Stopped PID {pid}"

    message = (result.stderr or result.stdout or "").strip()
    return f"PID {pid} stop failed: {message}"


def get_npm_executable():
    return shutil.which("npm.cmd") or shutil.which("npm")


def http_get_text(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def http_post_json(url, payload, timeout=5):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def wait_for_http_ok(url, retries=12, delay=1):
    for _ in range(retries):
        try:
            status, _ = http_get_text(url, timeout=3)

            if 200 <= status < 300:
                return True
        except Exception:
            pass

        time.sleep(delay)

    return False


def run_frontend_build(project_name):
    frontend_path = os.path.join(WORKSPACE_DIR, project_name, "frontend")
    package_path = os.path.join(frontend_path, "package.json")

    if not os.path.exists(package_path):
        return False, "frontend/package.json not found."

    npm_path = get_npm_executable()

    if not npm_path:
        return False, "npm was not found."

    node_modules_path = os.path.join(frontend_path, "node_modules")

    if not os.path.exists(node_modules_path):
        install_result = subprocess.run(
            [npm_path, "install"],
            cwd=frontend_path,
            capture_output=True,
            text=True,
            timeout=300
        )

        if install_result.returncode != 0:
            return False, (
                "npm install failed:\n"
                + (install_result.stderr or install_result.stdout or "")
            )

    build_result = subprocess.run(
        [npm_path, "run", "build"],
        cwd=frontend_path,
        capture_output=True,
        text=True,
        timeout=180
    )

    if build_result.returncode != 0:
        return False, (
            "npm run build failed:\n"
            + (build_result.stderr or build_result.stdout or "")
        )

    return True, "frontend build passed."


def allocate_port(base_port, used_ports):
    port = base_port

    while port in used_ports:
        port += 1

    used_ports.add(port)
    return port


def find_dotnet_executable():
    dotnet_path = shutil.which("dotnet")

    if dotnet_path:
        return dotnet_path

    user_dotnet_path = os.path.join(
        os.path.expanduser("~"),
        ".dotnet",
        "dotnet.exe"
    )

    if os.path.exists(user_dotnet_path):
        return user_dotnet_path

    return None


def ensure_project_config(project_name, stack_key=None):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    os.makedirs(project_path, exist_ok=True)

    config_path = os.path.join(project_path, "project_config.json")

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing_config = json.load(f)

            if (
                existing_config.get("frontend_port")
                and existing_config.get("backend_port")
            ):
                return existing_config
        except Exception:
            pass

    stack_key = stack_key or get_project_stack_key(project_name)
    used_ports = get_existing_project_ports(exclude_project=project_name)
    frontend_port = allocate_port(5173, used_ports)
    backend_port = allocate_port(get_default_backend_port(stack_key), used_ports)

    config = {
        "project_name": project_name,
        "stack_key": stack_key,
        "frontend_host": "127.0.0.1",
        "backend_host": "127.0.0.1",
        "frontend_port": frontend_port,
        "backend_port": backend_port,
        "frontend_url": f"http://127.0.0.1:{frontend_port}",
        "backend_url": f"http://127.0.0.1:{backend_port}"
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    return config

def capture_process_output(project_name, process_name, stream):
    log_path = get_runtime_log_paths(project_name).get(process_name)

    while True:

        line = stream.readline()

        if not line:
            break

        if project_name in FULLSTACK_LOGS:
            FULLSTACK_LOGS[project_name][process_name] += line

        if log_path:
            try:
                with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(line)
            except Exception:
                pass

def run_fullstack_project(project_name):

    config = ensure_project_config(project_name)
    ports = [
        config.get("backend_port"),
        config.get("frontend_port")
    ]

    if project_name in FULLSTACK_PROCESSES or find_pids_listening_on_ports(ports):
        return f"Fullstack project is already running: {project_name}"

    project_path = os.path.join("workspace", project_name)
    backend_path = os.path.join(project_path, "backend")
    frontend_path = os.path.join(project_path, "frontend")
    stack_key = config.get("stack_key", get_project_stack_key(project_name))
    backend_url = config["backend_url"]
    frontend_url = config["frontend_url"]
    log_paths = get_runtime_log_paths(project_name)

    for log_path in log_paths.values():
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"Runtime log for {project_name} started at {datetime.now().isoformat(timespec='seconds')}\n")
        except Exception:
            pass

    # -------------------------
    # Auto install Python deps
    # -------------------------

    requirements_path = os.path.join(
        backend_path,
        "requirements.txt"
    )

    if os.path.exists(requirements_path):

        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                "requirements.txt"
            ],
            cwd=backend_path,
            capture_output=True,
            text=True,
            timeout=300
        )

    # -------------------------
    # Auto install npm deps
    # -------------------------

    node_modules_path = os.path.join(
        frontend_path,
        "node_modules"
    )

    if not os.path.exists(node_modules_path):

        subprocess.run(
            ["npm", "install"],
            cwd=frontend_path,
            capture_output=True,
            text=True,
            timeout=300,
            shell=True
        )

    # -------------------------
    # Start backend
    # -------------------------

    backend_env = os.environ.copy()
    backend_env["PORT"] = str(config["backend_port"])
    backend_env["FRONTEND_URL"] = frontend_url
    backend_env["BACKEND_URL"] = backend_url

    if stack_key == "react_dotnet_sqlite":
        dotnet_path = find_dotnet_executable()

        if not dotnet_path:
            return """
ASP.NET backend cannot start because dotnet was not found.

Install the .NET SDK, then restart this project.

Download:
https://dotnet.microsoft.com/download
"""

        dotnet_dir = os.path.dirname(dotnet_path)
        backend_env["DOTNET_ROOT"] = dotnet_dir
        backend_env["PATH"] = dotnet_dir + os.pathsep + backend_env.get("PATH", "")

        subprocess.run(
            [dotnet_path, "restore"],
            cwd=backend_path,
            capture_output=True,
            text=True,
            timeout=300,
            env=backend_env
        )

        backend_process = subprocess.Popen(
            [dotnet_path, "run", "--urls", backend_url],
            cwd=backend_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=backend_env
        )
    elif stack_key == "react_php_sqlite":
        if not shutil.which("php"):
            return """
PHP backend cannot start because php was not found.

Install PHP or add it to PATH, then restart this project.
"""

        backend_process = subprocess.Popen(
            [
                "php",
                "-S",
                f"127.0.0.1:{config['backend_port']}",
                "-t",
                "backend"
            ],
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            env=backend_env
        )
    else:
        backend_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "flask",
                "--app",
                "app",
                "run",
                "--host",
                "127.0.0.1",
                "--port",
                str(config["backend_port"])
            ],
            cwd=backend_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=backend_env
        )

    # -------------------------
    # Start frontend
    # -------------------------

    frontend_process = subprocess.Popen(
        [
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(config["frontend_port"]),
            "--strictPort"
        ],
        cwd=frontend_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=True
    )

    FULLSTACK_PROCESSES[project_name] = {
        "backend": backend_process,
        "frontend": frontend_process
    }

    FULLSTACK_LOGS[project_name] = {
        "backend": "",
        "frontend": ""
    }

    runtime_state = save_project_runtime_state(
        project_name,
        config,
        FULLSTACK_PROCESSES[project_name]
    )

    for process_name, process in FULLSTACK_PROCESSES[project_name].items():
        threading.Thread(
            target=capture_process_output,
            args=(project_name, process_name, process.stdout),
            daemon=True
        ).start()

        threading.Thread(
            target=capture_process_output,
            args=(project_name, process_name, process.stderr),
            daemon=True
        ).start()

    return f"""
✅ FULLSTACK PROJECT STARTED

Backend:
{backend_url}

Frontend:
{frontend_url}

Runtime state:
workspace/_runtime/state.json

Log files:
Backend: {runtime_state["log_files"]["backend"]}
Frontend: {runtime_state["log_files"]["frontend"]}
"""


def stop_fullstack_project(project_name):
    import subprocess

    processes = FULLSTACK_PROCESSES.get(project_name)
    config = get_project_config(project_name)
    ports = [
        config.get("backend_port"),
        config.get("frontend_port")
    ]

    stopped = []

    if processes:
        for name, process in processes.items():
            try:
                stopped.append(taskkill_process_tree(process.pid))
            except Exception as e:
                stopped.append(f"{name} stop failed: {e}")

        del FULLSTACK_PROCESSES[project_name]

    for pid in get_runtime_state_pids(project_name):
        try:
            stopped.append(taskkill_process_tree(pid))
        except Exception as e:
            stopped.append(f"stored PID {pid} stop failed: {e}")

    listening_pids = find_pids_listening_on_ports(ports)

    for pid in sorted(listening_pids):
        stopped.append(taskkill_process_tree(pid))

    clear_project_runtime_state(project_name)

    if not stopped:
        stopped.append("No running processes found for assigned project ports.")

    log_project_activity(
        project_name,
        "FULLSTACK_STOPPED",
        f"Stopped: {', '.join(stopped)}"
    )

    return f"""
✅ Stopped fullstack project: {project_name}

Stopped:
{chr(10).join(stopped)}
"""


def stop_all_fullstack_projects():
    stopped = []
    runtime_state = read_runtime_state()

    for project_name in list(FULLSTACK_PROCESSES.keys()):
        result = stop_fullstack_project(project_name)
        stopped.append(result.strip())

    for project_name in list(runtime_state.keys()):
        if project_name in FULLSTACK_PROCESSES:
            continue

        result = stop_fullstack_project(project_name)
        stopped.append(result.strip())

    project_ports = []

    for project_name in list_workspace_projects():
        config = get_project_config(project_name, create_if_missing=False)

        if not config:
            continue

        project_ports.extend([
            config.get("backend_port"),
            config.get("frontend_port")
        ])

    listening_pids = find_pids_listening_on_ports(project_ports)

    for pid in sorted(listening_pids):
        stopped.append(taskkill_process_tree(pid))

    if not stopped:
        stopped.append("No running app processes found.")

    return f"""
STOP ALL RUNNING APPS COMPLETE

RESULTS:
{chr(10).join(stopped)}
"""


def reset_project_database(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    stop_result = stop_fullstack_project(project_name)

    database_candidates = [
        os.path.join(project_path, "backend", "app.db"),
        os.path.join(project_path, "app.db")
    ]

    removed = []
    missing = []
    failed = []

    for database_path in database_candidates:
        if not os.path.exists(database_path):
            missing.append(database_path)
            continue

        try:
            os.remove(database_path)
            removed.append(database_path)
        except Exception as e:
            failed.append(f"{database_path}: {e}")

    log_project_activity(
        project_name,
        "PROJECT_DATABASE_RESET",
        f"Removed:\n{chr(10).join(removed) if removed else 'None'}"
    )

    return f"""
PROJECT DATABASE RESET COMPLETE

PROJECT:
{project_name}

REMOVED DATABASE FILES:
{chr(10).join(removed) if removed else "None"}

FAILED:
{chr(10).join(failed) if failed else "None"}

STOP RESULT:
{stop_result}
"""


def get_latest_snapshot_name(project_name):
    snapshots_dir = os.path.join(WORKSPACE_DIR, "_snapshots", project_name)

    if not os.path.exists(snapshots_dir):
        return None

    snapshots = [
        name
        for name in os.listdir(snapshots_dir)
        if os.path.isdir(os.path.join(snapshots_dir, name))
    ]

    if not snapshots:
        return None

    return sorted(snapshots, reverse=True)[0]


def get_latest_history_entry(project_name):
    history_file = os.path.join(
        WORKSPACE_DIR,
        "_history",
        f"{project_name}.log"
    )

    if not os.path.exists(history_file):
        return None

    try:
        with open(history_file, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return None

        entries = [
            entry.strip()
            for entry in content.split("---")
            if entry.strip()
        ]

        if not entries:
            return None

        return entries[-1]
    except Exception:
        return None


def _read_json_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _read_runtime_records(folder_name):
    records_dir = os.path.join(RUNTIME_DIR, folder_name)

    if not os.path.exists(records_dir):
        return []

    records = []

    for file_name in os.listdir(records_dir):
        if not file_name.endswith(".json"):
            continue

        record = _read_json_file(os.path.join(records_dir, file_name))

        if record:
            records.append(record)

    records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return records


def get_latest_codegen_session_for_project(project_name):
    for session in _read_runtime_records("codegen_sessions"):
        if session.get("project_name") == project_name:
            return session

    return None


def get_latest_codegen_checkpoint_for_project(project_name):
    project_prefix = f"{project_name}/"

    for checkpoint in _read_runtime_records("codegen_checkpoints"):
        for file in checkpoint.get("files", []):
            file_path = (
                file.get("display_path")
                or file.get("relative_path", "")
            ).replace("\\", "/")

            if file_path.startswith(project_prefix):
                return checkpoint

    return None


def get_project_file_summary(project_path):
    ignored_dirs = {
        "node_modules",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "dist",
        ".vite",
    }
    summary = {
        "total_files": 0,
        "backend_files": 0,
        "frontend_files": 0,
    }

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in ignored_dirs
        ]

        for file_name in files:
            relative_path = os.path.relpath(
                os.path.join(root, file_name),
                project_path,
            ).replace("\\", "/")

            summary["total_files"] += 1

            if relative_path.startswith("backend/"):
                summary["backend_files"] += 1

            if relative_path.startswith("frontend/"):
                summary["frontend_files"] += 1

    return summary


def _status_from_validation_output(validation_output):
    if not validation_output:
        return "not_run"

    if any(marker in validation_output for marker in ["FAIL:", "NEEDS ATTENTION", "NEEDS FIX"]):
        return "failed"

    return "passed"


def get_project_dashboard(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return {
            "exists": False,
            "project_name": project_name,
            "error": f"Project not found: {project_name}"
        }

    config = get_project_config(project_name)
    runtime_state = get_project_runtime_state(project_name)
    stack_key = config.get("stack_key", get_project_stack_key(project_name))
    backend_port = config.get("backend_port")
    frontend_port = config.get("frontend_port")
    database_files = [
        os.path.join(project_path, "backend", "app.db"),
        os.path.join(project_path, "app.db")
    ]
    existing_databases = [
        path
        for path in database_files
        if os.path.exists(path)
    ]
    required_files = get_required_files_for_stack(stack_key)
    missing_required_files = [
        relative_path
        for relative_path in required_files
        if not os.path.exists(os.path.join(project_path, relative_path))
    ]
    latest_session = get_latest_codegen_session_for_project(project_name)
    latest_checkpoint = get_latest_codegen_checkpoint_for_project(project_name)
    validation_output = (latest_session or {}).get("validation_output", "")
    validation_status = (
        (latest_session or {}).get("validation_status")
        or _status_from_validation_output(validation_output)
    )
    file_summary = get_project_file_summary(project_path)

    return {
        "exists": True,
        "project_name": project_name,
        "stack_key": stack_key,
        "project_path": project_path,
        "frontend_url": config.get("frontend_url"),
        "backend_url": config.get("backend_url"),
        "frontend_port": frontend_port,
        "backend_port": backend_port,
        "frontend_running": is_port_listening(frontend_port),
        "backend_running": is_port_listening(backend_port),
        "database_exists": bool(existing_databases),
        "database_files": existing_databases,
        "latest_snapshot": get_latest_snapshot_name(project_name),
        "latest_history_entry": get_latest_history_entry(project_name),
        "runtime_state": runtime_state,
        "runtime_started_at": runtime_state.get("started_at"),
        "runtime_backend_pid": runtime_state.get("backend_pid"),
        "runtime_frontend_pid": runtime_state.get("frontend_pid"),
        "runtime_log_files": runtime_state.get("log_files", {}),
        "file_summary": file_summary,
        "required_files_total": len(required_files),
        "missing_required_files": missing_required_files,
        "latest_codegen_session": latest_session,
        "latest_codegen_checkpoint": latest_checkpoint,
        "latest_validation_status": validation_status,
        "latest_validation_output": validation_output,
        "quick_commands": [
            f"run fullstack {project_name}",
            f"validate app {project_name}",
            f"quality check {project_name}",
            f"show logs {project_name}",
            f"project history {project_name}",
        ],
    }


def validate_generated_app(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    config = ensure_project_config(project_name)
    stack_key = config.get("stack_key", get_project_stack_key(project_name))
    frontend_url = config["frontend_url"]
    backend_url = config["backend_url"]

    checks = []
    failures = []

    def add_check(ok, label, detail=""):
        status = "PASS" if ok else "FAIL"
        line = f"{status}: {label}"

        if detail:
            line += f" - {detail}"

        checks.append(line)

        if not ok:
            failures.append(line)

    required_files = get_required_files_for_stack(stack_key)

    for relative_path in required_files:
        file_path = os.path.join(project_path, relative_path)
        add_check(os.path.exists(file_path), f"required file {relative_path}")

    config_path = os.path.join(project_path, "project_config.json")
    add_check(os.path.exists(config_path), "project_config.json exists")
    add_check(bool(frontend_url), "frontend URL configured", frontend_url)
    add_check(bool(backend_url), "backend URL configured", backend_url)

    api_file = os.path.join(project_path, "frontend", "src", "api.js")

    if os.path.exists(api_file):
        with open(api_file, "r", encoding="utf-8") as f:
            api_code = f.read()

        add_check(
            backend_url in api_code,
            "frontend API points to assigned backend",
            backend_url
        )
    else:
        add_check(False, "frontend API points to assigned backend", "api.js missing")

    package_file = os.path.join(project_path, "frontend", "package.json")

    if os.path.exists(package_file):
        try:
            with open(package_file, "r", encoding="utf-8") as f:
                package_data = json.load(f)

            scripts = package_data.get("scripts", {})
            add_check("dev" in scripts, "frontend package has dev script")
            add_check("build" in scripts, "frontend package has build script")
        except Exception as e:
            add_check(False, "frontend package.json valid JSON", str(e))

    build_ok, build_detail = run_frontend_build(project_name)
    add_check(build_ok, "frontend production build", build_detail)

    backend_items_url = f"{backend_url}/api/items"

    if not wait_for_http_ok(backend_items_url, retries=3, delay=1):
        start_result = run_fullstack_project(project_name)
        add_check(
            "FULLSTACK PROJECT STARTED" in start_result
            or "already running" in start_result,
            "start fullstack project",
            start_result.strip()
        )

    backend_ready = wait_for_http_ok(backend_items_url, retries=15, delay=1)
    add_check(backend_ready, "backend GET /api/items responds", backend_items_url)

    inserted_title = "Validation test item"

    if backend_ready:
        try:
            status, _ = http_post_json(
                backend_items_url,
                {
                    "title": inserted_title,
                    "description": "Created by validator"
                },
                timeout=5
            )
            add_check(
                status in [200, 201],
                "backend POST /api/items accepts JSON",
                f"status {status}"
            )
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            add_check(False, "backend POST /api/items accepts JSON", body)
        except Exception as e:
            add_check(False, "backend POST /api/items accepts JSON", str(e))

        try:
            _, body = http_get_text(backend_items_url, timeout=5)
            add_check(
                inserted_title in body,
                "backend returns inserted validation item"
            )
        except Exception as e:
            add_check(False, "backend returns inserted validation item", str(e))

    frontend_ready = wait_for_http_ok(frontend_url, retries=10, delay=1)
    add_check(frontend_ready, "frontend server responds", frontend_url)

    if frontend_ready:
        try:
            _, frontend_api_code = http_get_text(f"{frontend_url}/src/api.js", timeout=5)
            add_check(
                backend_url in frontend_api_code,
                "running frontend serves correct api.js",
                backend_url
            )
        except Exception as e:
            add_check(False, "running frontend serves correct api.js", str(e))

    final_status = "READY" if not failures else "NEEDS ATTENTION"

    log_project_activity(
        project_name,
        "APP_VALIDATION_RUN",
        f"Final status: {final_status}\n" + "\n".join(checks)
    )

    return f"""
APP VALIDATION REPORT

PROJECT:
{project_name}

STACK:
{stack_key}

FRONTEND:
{frontend_url}

BACKEND:
{backend_url}

FINAL STATUS:
{final_status}

CHECKS:
{chr(10).join(checks)}
"""


def show_fullstack_logs(project_name):

    logs = get_fullstack_logs(project_name)
    runtime_state = get_project_runtime_state(project_name)
    log_files = runtime_state.get("log_files", {})

    if not logs.get("backend") and not logs.get("frontend") and not log_files:
        return "No logs found. Start the fullstack project first."

    backend_logs = logs.get("backend", "")
    frontend_logs = logs.get("frontend", "")

    if not backend_logs:
        backend_logs = "No backend logs captured yet."

    if not frontend_logs:
        frontend_logs = "No frontend logs captured yet."

    return f"""
===== BACKEND LOGS =====
{backend_logs}

===== FRONTEND LOGS =====
{frontend_logs}

===== LOG FILES =====
Backend: {log_files.get("backend", "None")}
Frontend: {log_files.get("frontend", "None")}
"""


def run_project_file(project_name, file_name):

    full_path = os.path.join(WORKSPACE_DIR, project_name, file_name)

    try:

        process = subprocess.Popen(
            [sys.executable, full_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            stdout, stderr = process.communicate(timeout=5)

            combined = (stdout or "") + "\n" + (stderr or "")

            return {
                "stdout": stdout,
                "stderr": stderr,
                "combined": combined,
                "returncode": process.returncode
            }

        except subprocess.TimeoutExpired:

            process.kill()

            return {
                "stdout": "Flask app started successfully",
                "stderr": "",
                "combined": "Flask app started successfully",
                "returncode": 0
            }

    except Exception as e:

        return {
            "stdout": "",
            "stderr": str(e),
            "combined": str(e),
            "returncode": 1
        }


def extract_error_summary(stderr):

    if not stderr:
        return "No error"

    lines = stderr.split("\n")

    for line in reversed(lines):
        if "Error" in line or "Exception" in line:
            return line

    return stderr.strip()

def get_fullstack_logs(project_name):

    logs = {
        "backend": "",
        "frontend": ""
    }

    if project_name in FULLSTACK_LOGS:
        logs["backend"] = FULLSTACK_LOGS[project_name].get("backend", "")
        logs["frontend"] = FULLSTACK_LOGS[project_name].get("frontend", "")

    runtime_state = get_project_runtime_state(project_name)
    log_files = runtime_state.get("log_files", {})

    if not logs["backend"]:
        logs["backend"] = read_runtime_log_file(log_files.get("backend"))

    if not logs["frontend"]:
        logs["frontend"] = read_runtime_log_file(log_files.get("frontend"))

    return logs

import re


def install_python_package(package_name, project_name=None):

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
            timeout=120
        )

        return result.stdout + "\n" + result.stderr

    except Exception as e:
        return str(e)


def install_npm_package(project_name, package_name):

    frontend_path = os.path.join(WORKSPACE_DIR, project_name, "frontend")

    try:
        result = subprocess.run(
            ["npm", "install", package_name],
            cwd=frontend_path,
            capture_output=True,
            text=True,
            timeout=120,
            shell=True
        )

        return result.stdout + "\n" + result.stderr

    except Exception as e:
        return str(e)


def detect_missing_python_package(log_text):

    match = re.search(
        r"ModuleNotFoundError: No module named '([^']+)'",
        log_text
    )

    if match:
        return match.group(1)

    return None


def detect_missing_npm_package(log_text):

    patterns = [
        r"Failed to resolve import \"([^\"]+)\"",
        r"Cannot find module '([^']+)'",
        r"Module not found: Error: Can't resolve '([^']+)'"
    ]

    for pattern in patterns:
        match = re.search(pattern, log_text)

        if match:
            package_name = match.group(1)

            if package_name.startswith(".") or package_name.startswith("/"):
                return None

            return package_name

    return None


def restart_fullstack_project(project_name):

    stop_fullstack_project(project_name)

    return run_fullstack_project(project_name)

def create_project_snapshot(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    snapshots_dir = os.path.join(WORKSPACE_DIR, "_snapshots", project_name)
    os.makedirs(snapshots_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_name = timestamp
    snapshot_path = os.path.join(snapshots_dir, snapshot_name)
    suffix = 2

    while os.path.exists(snapshot_path):
        snapshot_name = f"{timestamp}_{suffix}"
        snapshot_path = os.path.join(snapshots_dir, snapshot_name)
        suffix += 1

    shutil.copytree(
        project_path,
        snapshot_path,
        ignore=ignore_snapshot_files
    )

    log_project_activity(
        project_name,
        "SNAPSHOT_CREATED",
        f"Snapshot created successfully."
    )

    return f"""
✅ SNAPSHOT CREATED

PROJECT:
{project_name}

SNAPSHOT:
{snapshot_name}

NOTE:
node_modules and cache folders were ignored.
"""


def list_project_snapshots(project_name):
    snapshots_dir = os.path.join(WORKSPACE_DIR, "_snapshots", project_name)

    if not os.path.exists(snapshots_dir):
        return "No snapshots found."

    snapshots = sorted(os.listdir(snapshots_dir), reverse=True)

    return f"""
📦 SNAPSHOTS FOR {project_name}

{chr(10).join(snapshots)}
"""


def restore_project_snapshot(project_name, snapshot_name=None):

    # stop fullstack before restore if running
    try:
        stop_fullstack_project(project_name)
    except Exception:
        pass

    project_path = os.path.join(WORKSPACE_DIR, project_name)
    snapshots_dir = os.path.join(WORKSPACE_DIR, "_snapshots", project_name)

    if not os.path.exists(snapshots_dir):
        return "No snapshots found."

    snapshots = sorted(os.listdir(snapshots_dir), reverse=True)

    if not snapshots:
        return "No snapshots found."

    if snapshot_name is None:
        snapshot_name = snapshots[0]

    snapshot_path = os.path.join(snapshots_dir, snapshot_name)

    if not os.path.exists(snapshot_path):
        return f"Snapshot not found: {snapshot_name}"

    if os.path.exists(project_path):
        shutil.rmtree(project_path, ignore_errors=True)

    shutil.copytree(
        snapshot_path,
        project_path,
        ignore=ignore_snapshot_files
    )

    log_project_activity(
        project_name,
        "PROJECT_RESTORED",
        f"Snapshot restored: {snapshot_name}"
    )

    return f"""
✅ PROJECT RESTORED

PROJECT:
{project_name}

SNAPSHOT:
{snapshot_name}

NOTE:
node_modules was not restored. Run npm install inside frontend if needed.
"""

def ignore_snapshot_files(dir, names):
    ignored = {
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        ".vite"
    }

    return [name for name in names if name in ignored]


def get_readable_files(base_path):
    ignored_folders = {
        "node_modules",
        "__pycache__",
        ".git",
        "venv",
        ".venv",
        "dist",
        ".vite"
    }

    allowed_extensions = {
        ".py",
        ".js",
        ".jsx",
        ".json",
        ".html",
        ".css",
        ".txt",
        ".md"
    }

    result = {}

    for root, dirs, files in os.walk(base_path):
        dirs[:] = [
            d for d in dirs
            if d not in ignored_folders
        ]

        for file in files:
            ext = os.path.splitext(file)[1]

            if ext not in allowed_extensions:
                continue

            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, base_path)

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    result[relative_path] = f.read()
            except Exception:
                continue

    return result


def compare_project_snapshot(project_name, snapshot_name=None):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    snapshots_dir = os.path.join(WORKSPACE_DIR, "_snapshots", project_name)

    if not os.path.exists(project_path):
        return f"Project not found: {project_name}"

    if not os.path.exists(snapshots_dir):
        return "No snapshots found."

    snapshots = sorted(os.listdir(snapshots_dir), reverse=True)

    if not snapshots:
        return "No snapshots found."

    if snapshot_name is None:
        snapshot_name = snapshots[0]

    snapshot_path = os.path.join(snapshots_dir, snapshot_name)

    if not os.path.exists(snapshot_path):
        return f"Snapshot not found: {snapshot_name}"

    current_files = get_readable_files(project_path)
    snapshot_files = get_readable_files(snapshot_path)

    current_set = set(current_files.keys())
    snapshot_set = set(snapshot_files.keys())

    added = sorted(current_set - snapshot_set)
    removed = sorted(snapshot_set - current_set)

    modified = sorted([
        file
        for file in current_set.intersection(snapshot_set)
        if current_files[file] != snapshot_files[file]
    ])

    return f"""
📊 SNAPSHOT COMPARISON

PROJECT:
{project_name}

SNAPSHOT:
{snapshot_name}

ADDED FILES:
{chr(10).join(added) if added else "None"}

REMOVED FILES:
{chr(10).join(removed) if removed else "None"}

MODIFIED FILES:
{chr(10).join(modified) if modified else "None"}
"""

def restore_missing_project_files(project_name, snapshot_name=None):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    snapshots_dir = os.path.join(WORKSPACE_DIR, "_snapshots", project_name)

    if not os.path.exists(snapshots_dir):
        return "No snapshots found."

    snapshots = sorted(os.listdir(snapshots_dir), reverse=True)

    if not snapshots:
        return "No snapshots found."

    if snapshot_name is None:
        snapshot_name = snapshots[0]

    snapshot_path = os.path.join(snapshots_dir, snapshot_name)

    if not os.path.exists(snapshot_path):
        return f"Snapshot not found: {snapshot_name}"

    restored = []

    for root, dirs, files in os.walk(snapshot_path):
        dirs[:] = [
            d for d in dirs
            if d not in [
                "node_modules",
                "__pycache__",
                ".git",
                "venv",
                ".venv",
                "dist",
                ".vite"
            ]
        ]

        for file in files:
            snapshot_file_path = os.path.join(root, file)
            relative_path = os.path.relpath(snapshot_file_path, snapshot_path)
            current_file_path = os.path.join(project_path, relative_path)

            if not os.path.exists(current_file_path):
                os.makedirs(os.path.dirname(current_file_path), exist_ok=True)
                shutil.copy2(snapshot_file_path, current_file_path)
                restored.append(relative_path)

    log_project_activity(
        project_name,
        "MISSING_FILES_RESTORED",
        f"Snapshot: {snapshot_name}\nFiles:\n{chr(10).join(restored) if restored else 'None'}"
    )

    return f"""
✅ MISSING FILES RESTORED

PROJECT:
{project_name}

SNAPSHOT:
{snapshot_name}

RESTORED FILES:
{chr(10).join(restored) if restored else "No missing files found."}
"""

def log_project_activity(project_name, action, details=""):
    from datetime import datetime

    history_dir = os.path.join(WORKSPACE_DIR, "_history")
    os.makedirs(history_dir, exist_ok=True)

    history_file = os.path.join(history_dir, f"{project_name}.log")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = f"[{timestamp}] {action}"

    if details:
        entry += f"\n{details}"

    entry += "\n---\n"

    with open(history_file, "a", encoding="utf-8") as f:
        f.write(entry)


def get_project_history(project_name):
    history_file = os.path.join(
        WORKSPACE_DIR,
        "_history",
        f"{project_name}.log"
    )

    if not os.path.exists(history_file):
        return "No project history found."

    with open(history_file, "r", encoding="utf-8") as f:
        return f.read()

def restore_changed_project_files(project_name, snapshot_name=None):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    snapshots_dir = os.path.join(WORKSPACE_DIR, "_snapshots", project_name)

    if not os.path.exists(snapshots_dir):
        return "No snapshots found."

    snapshots = sorted(os.listdir(snapshots_dir), reverse=True)

    if not snapshots:
        return "No snapshots found."

    if snapshot_name is None:
        snapshot_name = snapshots[0]

    snapshot_path = os.path.join(snapshots_dir, snapshot_name)

    if not os.path.exists(snapshot_path):
        return f"Snapshot not found: {snapshot_name}"

    current_files = get_readable_files(project_path)
    snapshot_files = get_readable_files(snapshot_path)

    restored = []

    for file_name, snapshot_content in snapshot_files.items():
        current_content = current_files.get(file_name)

        if current_content != snapshot_content:
            source_path = os.path.join(snapshot_path, file_name)
            target_path = os.path.join(project_path, file_name)

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(source_path, target_path)

            restored.append(file_name)

    log_project_activity(
        project_name,
        "CHANGED_FILES_RESTORED",
        f"Snapshot: {snapshot_name}\nFiles:\n{chr(10).join(restored) if restored else 'None'}"
    )

    return f"""
✅ CHANGED FILES RESTORED

PROJECT:
{project_name}

SNAPSHOT:
{snapshot_name}

RESTORED FILES:
{chr(10).join(restored) if restored else "No changed files found."}
"""

def preflight_fullstack_project(project_name):

    project_path = os.path.join(WORKSPACE_DIR, project_name)

    checks = []

    backend_app = os.path.join(project_path, "backend", "app.py")
    backend_routes = os.path.join(project_path, "backend", "routes.py")
    backend_database = os.path.join(project_path, "backend", "database.py")

    frontend_package = os.path.join(project_path, "frontend", "package.json")
    frontend_app = os.path.join(project_path, "frontend", "src", "App.jsx")

    required_files = [
        backend_app,
        backend_routes,
        backend_database,
        frontend_package,
        frontend_app
    ]

    for file_path in required_files:

        if os.path.exists(file_path):
            checks.append(f"✅ EXISTS: {file_path}")
        else:
            checks.append(f"❌ MISSING: {file_path}")

    # Python syntax validation

    python_files = [
        backend_app,
        backend_routes,
        backend_database
    ]

    for file_path in python_files:

        if not os.path.exists(file_path):
            continue

        try:

            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            ast.parse(source)

            checks.append(
                f"✅ PYTHON OK: {os.path.basename(file_path)}"
            )

        except Exception as e:

            checks.append(
                f"❌ PYTHON ERROR: {os.path.basename(file_path)} -> {e}"
            )

    # package.json validation

    if os.path.exists(frontend_package):

        try:

            with open(frontend_package, "r", encoding="utf-8") as f:
                package_data = json.load(f)

            scripts = package_data.get("scripts", {})

            if "dev" in scripts:
                checks.append("✅ package.json dev script found")
            else:
                checks.append("❌ package.json missing dev script")

        except Exception as e:

            checks.append(
                f"❌ package.json invalid JSON -> {e}"
            )

    log_project_activity(
        project_name,
        "PREFLIGHT_CHECK",
        "\n".join(checks)
    )

    return f"""
🔍 PREFLIGHT REPORT

PROJECT:
{project_name}

RESULTS:
{chr(10).join(checks)}
"""
