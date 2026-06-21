import os
import importlib

import streamlit as st

import tools
import agent


importlib.invalidate_caches()
tools = importlib.reload(tools)
agent = importlib.reload(agent)
SUPPORTED_APP_STACKS = agent.SUPPORTED_APP_STACKS
run_agent = agent.run_agent


WORKSPACE_DIR = "workspace"
MODEL_SUGGESTIONS = [
    "llama3.2:1b",
    "qwen2.5-coder:1.5b",
    "phi3",
]


def list_projects():
    if not os.path.exists(WORKSPACE_DIR):
        return []

    return sorted(
        name
        for name in os.listdir(WORKSPACE_DIR)
        if os.path.isdir(os.path.join(WORKSPACE_DIR, name))
        and not name.startswith("_")
    )


def status_text(is_running):
    return "Running" if is_running else "Stopped"


def render_project_dashboard(project_name):
    dashboard = tools.get_project_dashboard(project_name)

    if not dashboard.get("exists"):
        st.warning(dashboard.get("error", "Project not found."))
        return

    st.subheader("Project dashboard")

    col1, col2, col3 = st.columns(3)
    col1.metric("Stack", dashboard["stack_key"])
    col2.metric("Frontend", status_text(dashboard["frontend_running"]))
    col3.metric("Backend", status_text(dashboard["backend_running"]))

    col4, col5 = st.columns(2)
    col4.markdown(f"**Frontend URL:** [{dashboard['frontend_url']}]({dashboard['frontend_url']})")
    col5.markdown(f"**Backend URL:** [{dashboard['backend_url']}]({dashboard['backend_url']})")

    col6, col7, col8 = st.columns(3)
    col6.metric("Frontend port", dashboard["frontend_port"])
    col7.metric("Backend port", dashboard["backend_port"])
    col8.metric("Database", "Exists" if dashboard["database_exists"] else "Not found")

    st.caption(f"Project path: {dashboard['project_path']}")

    if dashboard.get("runtime_started_at"):
        st.caption(
            "Runtime: "
            f"started {dashboard['runtime_started_at']} "
            f"(backend PID {dashboard.get('runtime_backend_pid')}, "
            f"frontend PID {dashboard.get('runtime_frontend_pid')})"
        )

    runtime_log_files = dashboard.get("runtime_log_files") or {}

    if runtime_log_files:
        st.caption(
            "Runtime logs: "
            + ", ".join(
                f"{name}: {path}"
                for name, path in runtime_log_files.items()
            )
        )

    if dashboard["database_files"]:
        st.caption("Database: " + ", ".join(dashboard["database_files"]))

    if dashboard["latest_snapshot"]:
        st.caption(f"Latest snapshot: {dashboard['latest_snapshot']}")
    else:
        st.caption("Latest snapshot: none")

    if dashboard["latest_history_entry"]:
        with st.expander("Latest history entry"):
            st.code(dashboard["latest_history_entry"])


st.set_page_config(page_title="AI Coding Agent", layout="wide")

installed_models = agent.get_ollama_models()
model_options = installed_models or MODEL_SUGGESTIONS

if agent.OLLAMA_MODEL not in model_options:
    model_options = [agent.OLLAMA_MODEL] + model_options

selected_model = st.sidebar.selectbox(
    "Ollama model",
    model_options,
    index=model_options.index(agent.OLLAMA_MODEL),
)

custom_model = st.sidebar.text_input(
    "Custom model",
    value=selected_model,
)

active_model = agent.set_ollama_model(custom_model)
st.sidebar.caption(f"Active model: {active_model}")

st.title("AI Coding Agent")
st.caption("Build, modify, run, inspect generated apps, and generate standalone code.")

mode = st.radio(
    "Mode",
    [
        "Build a new app",
        "Modify an existing app",
        "Generate code",
        "Run or inspect a project",
        "Advanced command",
    ],
    horizontal=True,
)

projects = list_projects()
command = ""
direct_output = ""

if mode == "Build a new app":
    stack_options = {
        stack["label"]: stack_key
        for stack_key, stack in SUPPORTED_APP_STACKS.items()
    }

    selected_stack_label = st.selectbox(
        "Application stack",
        list(stack_options.keys()),
    )

    prompt = st.text_area(
        "Describe the app you want",
        placeholder="Example: Build a customer tracker with name, email, phone, notes, search, and a dashboard.",
        height=140,
    )

    if st.button("Build app", type="primary"):
        command = f"create app {prompt.strip()} using {selected_stack_label}"

elif mode == "Modify an existing app":
    if not projects:
        st.info("No generated projects found yet. Build a new app first.")

    project_name = st.selectbox("Project", projects) if projects else ""
    change_request = st.text_area(
        "Describe the change",
        placeholder="Example: Add search by customer name and email.",
        height=120,
    )

    if st.button("Modify app", type="primary", disabled=not projects):
        command = f"modify app {project_name} {change_request.strip()}"

elif mode == "Generate code":
    code_prompt = st.text_area(
        "Describe the code you want",
        placeholder="Example: Write a Python function that validates email addresses.",
        height=140,
    )
    save_to_file = st.checkbox("Save to file")
    save_path = ""

    if save_to_file:
        save_path = st.text_input(
            "Workspace path",
            placeholder="Example: snippets/email_validator.py",
        )

    if save_to_file:
        saved_preview = st.session_state.get("generated_code_preview")
        preview_matches_input = (
            saved_preview
            and saved_preview.get("path") == save_path.strip()
            and saved_preview.get("prompt") == code_prompt.strip()
        )
        overwrite_confirmed = False

        if preview_matches_input and saved_preview.get("exists"):
            overwrite_confirmed = st.checkbox("Confirm overwrite existing file")

        preview_col, save_col = st.columns(2)

        if preview_col.button("Preview file", type="primary"):
            if not save_path.strip() or not code_prompt.strip():
                direct_output = "Use format: preview code file <workspace_path> <prompt>"
            else:
                with st.spinner("Generating preview..."):
                    preview = agent.build_generated_code_preview(
                        save_path.strip(),
                        code_prompt.strip(),
                    )

                if preview["ok"]:
                    st.session_state["generated_code_preview"] = {
                        "path": save_path.strip(),
                        "prompt": code_prompt.strip(),
                        "code": preview["code"],
                        "exists": preview["exists"],
                        "output": preview["output"],
                    }
                else:
                    st.session_state.pop("generated_code_preview", None)

                direct_output = preview["output"]

        if save_col.button("Save file"):
            if not save_path.strip() or not code_prompt.strip():
                direct_output = "Use format: save code file <workspace_path> <prompt>"
            else:
                preview = st.session_state.get("generated_code_preview")

                if (
                    not preview
                    or preview.get("path") != save_path.strip()
                    or preview.get("prompt") != code_prompt.strip()
                ):
                    direct_output = (
                        "Please preview this exact path and prompt before saving."
                    )
                elif preview.get("exists") and not overwrite_confirmed:
                    direct_output = "Please confirm overwrite before saving this existing file."
                else:
                    direct_output = agent.save_code_content(
                        save_path.strip(),
                        preview["code"],
                    )
    else:
        if st.button("Generate code", type="primary"):
            command = f"generate code {code_prompt.strip()}"

elif mode == "Run or inspect a project":
    if not projects:
        st.info("No generated projects found yet. Build a new app first.")

    project_name = st.selectbox("Project", projects) if projects else ""

    if project_name:
        render_project_dashboard(project_name)

    action = st.selectbox(
        "Action",
        [
            "run fullstack",
            "stop fullstack",
            "stop all apps",
            "show logs",
            "validate app",
            "quality check",
            "preflight fullstack",
            "project history",
            "refresh project ports",
            "refresh project spec",
            "reset database",
            "snapshot",
        ],
    )

    if st.button("Run action", type="primary", disabled=not projects):
        if action == "stop all apps":
            command = action
        else:
            command = f"{action} {project_name}"

else:
    command_input = st.text_area(
        "Command",
        placeholder="Type help to see available commands.",
        height=120,
    )

    if st.button("Run command", type="primary"):
        command = command_input.strip()

if direct_output:
    st.subheader("Agent response")
    st.code(direct_output)
elif command:
    if command.endswith(" ") or command in ["create app", "modify app"]:
        st.warning("Please fill in the required input first.")
    else:
        with st.spinner("Agent is working..."):
            try:
                output = run_agent(command)
            except Exception as error:
                output = str(error)

        st.subheader("Agent response")
        st.code(output)
