import os

from agent_llm import invoke_llm
from agent_project_files import parse_llm_project_output, write_project
from agent_stacks import build_stack_instruction, get_project_stack_key, get_stack
from tools import create_project_snapshot, ensure_project_config, log_project_activity


WORKSPACE_DIR = "workspace"


def build_from_plan(
    project_name,
    create_fallback_project_files,
    apply_project_ports_to_files,
    validate_fullstack_structure,
    create_standalone_project_files,
):
    project_path = os.path.join(WORKSPACE_DIR, project_name)
    spec_path = os.path.join(project_path, "project_spec.json")

    if not os.path.exists(spec_path):
        return f"project_spec.json not found for project: {project_name}"

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = f.read()

    stack_key = get_project_stack_key(project_name)
    stack = get_stack(stack_key)
    project_config = ensure_project_config(project_name, stack_key)
    stack_instruction = build_stack_instruction(stack_key, project_config)

    prompt = f"""
You are a full-stack {stack["label"]} project builder.

Build a complete working app from this project specification.

PROJECT NAME:
{project_name}

PROJECT SPEC:
{spec}

Return ONLY raw project files.

{stack_instruction}

Universal rules:
- No markdown
- No explanation
- Every file must start with file:
- Do not generate files outside the requested project structure
"""

    response = invoke_llm(prompt)

    files_dict = parse_llm_project_output(response)

    if not files_dict:
        files_dict = create_fallback_project_files(stack_key)
    elif stack_key != "react_flask_sqlite":
        fallback_files = create_fallback_project_files(stack_key)

        for required_file in stack["required_files"]:
            if required_file not in files_dict and required_file in fallback_files:
                files_dict[required_file] = fallback_files[required_file]

    files_dict = apply_project_ports_to_files(files_dict, project_config, stack_key)

    write_project(project_name, files_dict)

    if stack_key == "react_flask_sqlite":
        structure_fixes = validate_fullstack_structure(project_name)
    else:
        structure_fixes = []

    standalone_files = create_standalone_project_files(project_name)

    log_project_activity(
        project_name,
        "BUILT_FROM_PLAN",
        f"Files:\n{chr(10).join(files_dict.keys())}",
    )

    create_project_snapshot(project_name)

    return f"""
PROJECT BUILT FROM PLAN

PROJECT:
workspace/{project_name}

FILES:
{chr(10).join(files_dict.keys())}

STRUCTURE FIXES:
{chr(10).join(structure_fixes) if structure_fixes else "None"}

STANDALONE FILES:
{chr(10).join(standalone_files)}

SNAPSHOT:
Created after build
"""
