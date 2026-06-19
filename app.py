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
st.caption("Build, modify, run, and inspect generated apps.")

mode = st.radio(
    "Mode",
    [
        "Build a new app",
        "Modify an existing app",
        "Run or inspect a project",
        "Advanced command",
    ],
    horizontal=True,
)

projects = list_projects()
command = ""

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

if command:
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
