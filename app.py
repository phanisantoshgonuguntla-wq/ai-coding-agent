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
CODEGEN_PROMPT_PRESETS = {
    "Add API route": "Add a backend API route and any frontend API helper needed to call it.",
    "Add React component": "Add a reusable React component with styling and wire it into the current UI.",
    "Add database field": "Add a new database field end to end, including schema, models, API handling, and UI display.",
    "Add export feature": "Add a CSV export feature for the main records in this project.",
    "Add search/filter": "Add search and filter support for the main records in this project.",
}


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


def validation_needs_repair(validation_output):
    failure_markers = [
        "FAIL:",
        "NEEDS ATTENTION",
        "NEEDS FIX",
    ]
    return any(marker in validation_output for marker in failure_markers)


def render_project_dashboard(project_name):
    dashboard = tools.get_project_dashboard(project_name)

    if not dashboard.get("exists"):
        st.warning(dashboard.get("error", "Project not found."))
        return

    st.subheader("Project dashboard")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Stack", dashboard["stack_key"])
    col2.metric("Frontend", status_text(dashboard["frontend_running"]))
    col3.metric("Backend", status_text(dashboard["backend_running"]))
    col4.metric("Validation", dashboard.get("latest_validation_status", "not_run"))

    col4, col5 = st.columns(2)
    col4.markdown(f"**Frontend URL:** [{dashboard['frontend_url']}]({dashboard['frontend_url']})")
    col5.markdown(f"**Backend URL:** [{dashboard['backend_url']}]({dashboard['backend_url']})")

    col6, col7, col8, col9 = st.columns(4)
    col6.metric("Frontend port", dashboard["frontend_port"])
    col7.metric("Backend port", dashboard["backend_port"])
    col8.metric("Database", "Exists" if dashboard["database_exists"] else "Not found")
    col9.metric("Files", dashboard.get("file_summary", {}).get("total_files", 0))

    st.caption(f"Project path: {dashboard['project_path']}")

    file_summary = dashboard.get("file_summary", {})
    st.caption(
        "Files: "
        f"backend {file_summary.get('backend_files', 0)}, "
        f"frontend {file_summary.get('frontend_files', 0)}"
    )

    missing_required_files = dashboard.get("missing_required_files", [])

    if missing_required_files:
        st.warning(
            "Missing required files: "
            + ", ".join(missing_required_files)
        )
    else:
        st.success(
            f"Required files present: {dashboard.get('required_files_total', 0)} checked"
        )

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

    latest_session = dashboard.get("latest_codegen_session")

    if latest_session:
        with st.expander("Latest codegen session"):
            st.write(f"ID: {latest_session.get('id')}")
            st.write(f"Type: {latest_session.get('type')}")
            st.write(f"Validation: {latest_session.get('validation_status')}")
            st.write(f"Checkpoint: {latest_session.get('checkpoint_id') or 'None'}")
            st.write(f"Created: {latest_session.get('created_at')}")
            st.code("\n".join(latest_session.get("files", [])) or "No files")
    else:
        st.caption("Latest codegen session: none")

    latest_checkpoint = dashboard.get("latest_codegen_checkpoint")

    if latest_checkpoint:
        with st.expander("Latest codegen checkpoint"):
            st.write(f"ID: {latest_checkpoint.get('id')}")
            st.write(f"Reason: {latest_checkpoint.get('reason')}")
            st.write(f"Created: {latest_checkpoint.get('created_at')}")
            st.code(
                "\n".join(
                    file.get("display_path", "")
                    for file in latest_checkpoint.get("files", [])
                ) or "No files"
            )
    else:
        st.caption("Latest codegen checkpoint: none")

    if dashboard.get("latest_validation_output"):
        with st.expander("Latest validation output"):
            st.code(dashboard["latest_validation_output"])

    with st.expander("Quick commands"):
        st.code("\n".join(dashboard.get("quick_commands", [])))

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
    with st.expander("Codegen history", expanded=False):
        sessions = agent.get_codegen_session_records()

        if not sessions:
            st.caption("No codegen sessions found.")
        else:
            session_options = {
                (
                    f"{session.get('created_at')} | "
                    f"{session.get('project_name')} | "
                    f"{session.get('validation_status')} | "
                    f"{session.get('id')}"
                ): session
                for session in sessions
            }
            selected_session_label = st.selectbox(
                "Session",
                list(session_options.keys()),
            )
            selected_session = session_options[selected_session_label]
            st.write(f"Checkpoint: {selected_session.get('checkpoint_id') or 'None'}")
            st.write(f"Files: {len(selected_session.get('files', []))}")
            st.code(agent.show_codegen_session(selected_session["id"]))

    preset_label = st.selectbox(
        "Prompt preset",
        ["Custom prompt"] + list(CODEGEN_PROMPT_PRESETS.keys()),
    )
    preset_prompt = CODEGEN_PROMPT_PRESETS.get(preset_label, "")
    code_prompt = st.text_area(
        "Describe the code you want",
        placeholder=preset_prompt or "Example: Write a Python function that validates email addresses.",
        height=140,
    )
    effective_code_prompt = code_prompt.strip() or preset_prompt
    save_to_file = st.checkbox("Save to file")
    multiple_files = False
    save_path = ""

    if save_to_file:
        multiple_files = st.checkbox("Generate multiple files")

    if save_to_file and not multiple_files:
        save_path = st.text_input(
            "Workspace path",
            placeholder="Example: snippets/email_validator.py",
        )

    if save_to_file and multiple_files:
        project_aware = False
        project_name = ""

        if projects:
            project_aware = st.checkbox("Use existing project context")

        if project_aware:
            project_name = st.selectbox("Project", projects)
            validate_after_save = st.checkbox("Validate after save")
            preview_repair_after_failure = False

            if validate_after_save:
                preview_repair_after_failure = st.checkbox(
                    "Preview repair if validation fails"
                )
        else:
            validate_after_save = False
            preview_repair_after_failure = False

        preview_state_key = (
            "project_code_files_preview"
            if project_aware
            else "generated_code_files_preview"
        )
        repair_state_key = "project_repair_files_preview"
        saved_preview = st.session_state.get(preview_state_key)
        preview_matches_input = (
            saved_preview
            and saved_preview.get("prompt") == effective_code_prompt
            and saved_preview.get("project_name", "") == project_name
        )
        overwrite_confirmed = False

        if preview_matches_input and saved_preview.get("has_existing_files"):
            overwrite_confirmed = st.checkbox("Confirm overwrite existing files")

        repair_preview = st.session_state.get(repair_state_key)
        repair_matches_input = (
            project_aware
            and repair_preview
            and repair_preview.get("prompt") == effective_code_prompt
            and repair_preview.get("project_name") == project_name
        )
        repair_overwrite_confirmed = False

        if repair_matches_input:
            if repair_preview.get("has_existing_files"):
                repair_overwrite_confirmed = st.checkbox(
                    "Confirm repair overwrite existing files"
                )

            if st.button("Save repair preview"):
                if repair_preview.get("has_existing_files") and not repair_overwrite_confirmed:
                    direct_output = "Please confirm overwrite before saving repair files."
                else:
                    direct_output = agent.save_code_files_content(
                        repair_preview["files"],
                    )
                    checkpoint_id = agent.extract_codegen_checkpoint_id(direct_output)
                    git_summary = agent.build_codegen_git_summary(
                        repair_preview["files"],
                        effective_code_prompt,
                    )
                    validation_output = ""

                    if validate_after_save:
                        with st.spinner("Validating repaired project changes..."):
                            try:
                                validation_output = agent.validate_codegen_changes(
                                    project_name,
                                    repair_preview["files"],
                                )
                            except Exception as error:
                                validation_output = str(error)

                        direct_output += (
                            "\n\n====================\n"
                            "REPAIR VALIDATION RESULT\n"
                            "====================\n"
                            f"{validation_output}"
                        )
                    else:
                        direct_output += (
                            "\n\nNEXT CHECK:\n"
                            f"validate app {project_name}"
                        )

                    direct_output += (
                        "\n\n====================\n"
                        f"{git_summary}"
                    )

                    session = agent.record_codegen_session(
                        "repair",
                        project_name,
                        effective_code_prompt,
                        repair_preview["files"],
                        validation_output,
                        repair_preview.get("dependency_warnings", []),
                        checkpoint_id,
                        git_summary,
                        repair_preview.get("implementation_plan", ""),
                    )
                    direct_output += (
                        "\n\nCODEGEN SESSION:\n"
                        f"{session['id']}"
                    )

        if project_aware and st.button("Explain context"):
            if not effective_code_prompt:
                direct_output = "Use format: explain project context <project_name> <prompt>"
            else:
                direct_output = agent.explain_project_context(
                    project_name,
                    effective_code_prompt,
                )

        preview_col, save_col = st.columns(2)

        if preview_col.button("Preview files", type="primary"):
            if not effective_code_prompt:
                direct_output = "Use format: preview code files <prompt>"
            else:
                with st.spinner("Generating file previews..."):
                    if project_aware:
                        preview = agent.build_project_code_files_preview(
                            project_name,
                            effective_code_prompt,
                        )
                    else:
                        preview = agent.build_generated_code_files_preview(
                            effective_code_prompt,
                        )

                if preview["ok"]:
                    st.session_state[preview_state_key] = {
                        "prompt": effective_code_prompt,
                        "project_name": project_name,
                        "files": preview["files"],
                        "has_existing_files": preview["has_existing_files"],
                        "dependency_warnings": preview.get("dependency_warnings", []),
                        "implementation_plan": preview.get("implementation_plan", ""),
                        "output": preview["output"],
                    }
                else:
                    st.session_state.pop(preview_state_key, None)

                direct_output = preview["output"]

        if save_col.button("Save files"):
            if not effective_code_prompt:
                direct_output = "Use format: save code files <prompt>"
            else:
                preview = st.session_state.get(preview_state_key)

                if (
                    not preview
                    or preview.get("prompt") != effective_code_prompt
                    or preview.get("project_name", "") != project_name
                ):
                    direct_output = "Please preview this exact prompt before saving."
                elif preview.get("has_existing_files") and not overwrite_confirmed:
                    direct_output = "Please confirm overwrite before saving existing files."
                else:
                    direct_output = agent.save_code_files_content(
                        preview["files"],
                    )
                    checkpoint_id = agent.extract_codegen_checkpoint_id(direct_output)
                    git_summary = agent.build_codegen_git_summary(
                        preview["files"],
                        effective_code_prompt,
                    )
                    validation_output = ""

                    if project_aware:
                        if validate_after_save:
                            with st.spinner("Validating saved project changes..."):
                                try:
                                    validation_output = agent.validate_codegen_changes(
                                        project_name,
                                        preview["files"],
                                    )
                                except Exception as error:
                                    validation_output = str(error)

                            direct_output += (
                                "\n\n====================\n"
                                "VALIDATION RESULT\n"
                                "====================\n"
                                f"{validation_output}"
                            )

                            if (
                                preview_repair_after_failure
                                and validation_needs_repair(validation_output)
                            ):
                                with st.spinner("Generating repair preview..."):
                                    repair_preview = agent.build_project_repair_files_preview(
                                        project_name,
                                        effective_code_prompt,
                                        validation_output,
                                    )

                                if repair_preview["ok"]:
                                    st.session_state[repair_state_key] = {
                                        "prompt": effective_code_prompt,
                                        "project_name": project_name,
                                        "files": repair_preview["files"],
                                        "has_existing_files": repair_preview["has_existing_files"],
                                        "dependency_warnings": repair_preview.get("dependency_warnings", []),
                                        "implementation_plan": repair_preview.get("implementation_plan", ""),
                                        "output": repair_preview["output"],
                                    }
                                else:
                                    st.session_state.pop(repair_state_key, None)

                                direct_output += (
                                    "\n\n====================\n"
                                    "REPAIR PREVIEW\n"
                                    "====================\n"
                                    f"{repair_preview['output']}"
                                )
                        else:
                            direct_output += (
                                "\n\nNEXT CHECK:\n"
                                f"validate app {project_name}"
                            )

                        direct_output += (
                            "\n\n====================\n"
                            f"{git_summary}"
                        )

                        session = agent.record_codegen_session(
                            "project_save",
                            project_name,
                            effective_code_prompt,
                            preview["files"],
                            validation_output,
                            preview.get("dependency_warnings", []),
                            checkpoint_id,
                            git_summary,
                            preview.get("implementation_plan", ""),
                        )
                        direct_output += (
                            "\n\nCODEGEN SESSION:\n"
                            f"{session['id']}"
                        )
                    else:
                        git_summary = agent.build_codegen_git_summary(
                            preview["files"],
                            effective_code_prompt,
                        )
                        direct_output += (
                            "\n\n====================\n"
                            f"{git_summary}"
                        )
    elif save_to_file:
        saved_preview = st.session_state.get("generated_code_preview")
        preview_matches_input = (
            saved_preview
            and saved_preview.get("path") == save_path.strip()
            and saved_preview.get("prompt") == effective_code_prompt
        )
        overwrite_confirmed = False

        if preview_matches_input and saved_preview.get("exists"):
            overwrite_confirmed = st.checkbox("Confirm overwrite existing file")

        preview_col, save_col = st.columns(2)

        if preview_col.button("Preview file", type="primary"):
            if not save_path.strip() or not effective_code_prompt:
                direct_output = "Use format: preview code file <workspace_path> <prompt>"
            else:
                with st.spinner("Generating preview..."):
                    preview = agent.build_generated_code_preview(
                        save_path.strip(),
                        effective_code_prompt,
                    )

                if preview["ok"]:
                    st.session_state["generated_code_preview"] = {
                        "path": save_path.strip(),
                        "prompt": effective_code_prompt,
                        "code": preview["code"],
                        "exists": preview["exists"],
                        "output": preview["output"],
                    }
                else:
                    st.session_state.pop("generated_code_preview", None)

                direct_output = preview["output"]

        if save_col.button("Save file"):
            if not save_path.strip() or not effective_code_prompt:
                direct_output = "Use format: save code file <workspace_path> <prompt>"
            else:
                preview = st.session_state.get("generated_code_preview")

                if (
                    not preview
                    or preview.get("path") != save_path.strip()
                    or preview.get("prompt") != effective_code_prompt
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
                    git_summary = agent.build_codegen_git_summary(
                        [
                            {
                                "display_path": save_path.strip().replace("\\", "/"),
                            }
                        ],
                        effective_code_prompt,
                    )
                    direct_output += (
                        "\n\n====================\n"
                        f"{git_summary}"
                    )
    else:
        if st.button("Generate code", type="primary"):
            command = f"generate code {effective_code_prompt}"

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
            "validation center",
            "repair guidance",
            "runtime health",
            "cleanup runtime",
            "dependency report",
            "project memory",
            "agent health",
            "quality check",
            "preflight fullstack",
            "project history",
            "refresh project ports",
            "refresh project spec",
            "reset database",
            "snapshot",
        ],
    )

    if st.button("Run action", type="primary", disabled=not projects and action != "agent health"):
        if action in ["stop all apps", "agent health"]:
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
