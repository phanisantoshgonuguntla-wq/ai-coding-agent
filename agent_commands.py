from dataclasses import dataclass

from agent_stacks import looks_like_app_build_request
from agent_text import make_safe_project_name, strip_command_prefix


@dataclass
class Command:
    name: str
    matches: object
    handle: object


def _after_phrase(user_input, phrase):
    index = user_input.lower().find(phrase)

    if index < 0:
        return ""

    return user_input[index + len(phrase):].strip()


def _generate_fullstack_project(user_input, ctx):
    response = ctx["generate_fullstack_project"](user_input)
    files_dict = ctx["parse_llm_project_output"](response)
    project_name = make_safe_project_name(user_input)
    ctx["write_project"](project_name, files_dict)
    structure_fixes = ctx["validate_fullstack_structure"](project_name)
    ctx["log_project_activity"](
        project_name,
        "FULLSTACK_PROJECT_CREATED",
        f"Files:\n{chr(10).join(files_dict.keys())}",
    )

    return f"""
FULL-STACK PROJECT CREATED SUCCESSFULLY

PROJECT:
workspace/{project_name}

FILES:
{chr(10).join(files_dict.keys())}

STRUCTURE FIXES:
{chr(10).join(structure_fixes)}
"""


def _generate_flask_project(user_input, ctx):
    response = ctx["generate_flask_project"](user_input)
    files_dict = ctx["parse_llm_project_output"](response)
    project_name = make_safe_project_name(user_input)
    ctx["write_project"](project_name, files_dict)
    structure_fixes = ctx["validate_flask_structure"](project_name)
    ctx["log_project_activity"](
        project_name,
        "FLASK_PROJECT_CREATED",
        f"Files:\n{chr(10).join(files_dict.keys())}",
    )

    return f"""
PROJECT CREATED SUCCESSFULLY

PROJECT:
workspace/{project_name}

FILES:
{chr(10).join(files_dict.keys())}

STRUCTURE FIXES:
{chr(10).join(structure_fixes)}
"""


def _restore_missing(user_input, ctx):
    parts = user_input.split()

    if len(parts) == 3:
        return ctx["restore_missing_project_files"](parts[2])

    if len(parts) == 4:
        return ctx["restore_missing_project_files"](parts[2], parts[3])

    return "Use format: restore missing <project_name> [snapshot_name]"


def _restore_changed(user_input, ctx):
    parts = user_input.split()

    if len(parts) == 3:
        return ctx["restore_changed_project_files"](parts[2])

    if len(parts) == 4:
        return ctx["restore_changed_project_files"](parts[2], parts[3])

    return "Use format: restore changed <project_name> [snapshot_name]"


def _restore_project(user_input, ctx):
    parts = user_input.split()

    if len(parts) == 2:
        return ctx["restore_project_snapshot"](parts[1])

    if len(parts) == 3:
        return ctx["restore_project_snapshot"](parts[1], parts[2])

    return "Use format: restore <project_name> [snapshot_name]"


def _compare_snapshot(user_input, ctx):
    parts = user_input.split()

    if len(parts) == 3:
        return ctx["compare_project_snapshot"](parts[2])

    if len(parts) == 4:
        return ctx["compare_project_snapshot"](parts[2], parts[3])

    return "Use format: compare snapshot <project_name> [snapshot_name]"


def _modify_app(user_input, ctx):
    parts = user_input.split(maxsplit=3)

    if len(parts) < 4:
        return "Use format: modify app <project_name> <change request>"

    return ctx["modify_app"](parts[2], parts[3])


def _add_feature(user_input, ctx):
    parts = user_input.split(maxsplit=3)

    if len(parts) < 4:
        return "Use format: add feature <project_name> <feature request>"

    return ctx["add_feature"](parts[2], parts[3])


def _generate_code_file(user_input, ctx):
    parts = strip_command_prefix(user_input, "generate code file").split(maxsplit=1)

    if len(parts) < 2:
        return "Use format: generate code file <workspace_path> <prompt>"

    return ctx["save_generated_code"](parts[0], parts[1])


def _preview_code_file(user_input, ctx):
    parts = strip_command_prefix(user_input, "preview code file").split(maxsplit=1)

    if len(parts) < 2:
        return "Use format: preview code file <workspace_path> <prompt>"

    return ctx["preview_generated_code_file"](parts[0], parts[1])


def _save_code_file(user_input, ctx):
    parts = strip_command_prefix(user_input, "save code file").split(maxsplit=1)

    if len(parts) < 2:
        return "Use format: save code file <workspace_path> <prompt>"

    return ctx["save_generated_code"](parts[0], parts[1])


def _preview_code_files(user_input, ctx):
    prompt = strip_command_prefix(user_input, "preview code files")

    if not prompt:
        return "Use format: preview code files <prompt>"

    return ctx["preview_generated_code_files"](prompt)


def _save_code_files(user_input, ctx):
    prompt = strip_command_prefix(user_input, "save code files")

    if not prompt:
        return "Use format: save code files <prompt>"

    return ctx["save_generated_code_files"](prompt)


def _preview_project_code(user_input, ctx):
    parts = strip_command_prefix(user_input, "preview project code").split(maxsplit=1)

    if len(parts) < 2:
        return "Use format: preview project code <project_name> <prompt>"

    return ctx["preview_project_code_files"](parts[0], parts[1])


def _save_project_code(user_input, ctx):
    parts = strip_command_prefix(user_input, "save project code").split(maxsplit=1)

    if len(parts) < 2:
        return "Use format: save project code <project_name> <prompt>"

    return ctx["save_generated_project_code_files"](parts[0], parts[1])


def build_command_registry(ctx):
    return [
        Command(
            "supported_stacks",
            lambda text, lower: lower in ["supported stacks", "list stacks", "stacks"],
            lambda text: ctx["list_supported_stacks"](),
        ),
        Command(
            "plan_app",
            lambda text, lower: lower.startswith("plan app "),
            lambda text: ctx["plan_app"](text),
        ),
        Command(
            "create_app",
            lambda text, lower: lower.startswith("create app "),
            lambda text: ctx["create_app_workflow"](text),
        ),
        Command(
            "preview_project_code",
            lambda text, lower: lower == "preview project code" or lower.startswith("preview project code "),
            lambda text: _preview_project_code(text, ctx),
        ),
        Command(
            "save_project_code",
            lambda text, lower: lower == "save project code" or lower.startswith("save project code "),
            lambda text: _save_project_code(text, ctx),
        ),
        Command(
            "preview_code_files",
            lambda text, lower: lower == "preview code files" or lower.startswith("preview code files "),
            lambda text: _preview_code_files(text, ctx),
        ),
        Command(
            "save_code_files",
            lambda text, lower: lower == "save code files" or lower.startswith("save code files "),
            lambda text: _save_code_files(text, ctx),
        ),
        Command(
            "preview_code_file",
            lambda text, lower: lower == "preview code file" or lower.startswith("preview code file "),
            lambda text: _preview_code_file(text, ctx),
        ),
        Command(
            "save_code_file",
            lambda text, lower: lower == "save code file" or lower.startswith("save code file "),
            lambda text: _save_code_file(text, ctx),
        ),
        Command(
            "generate_code_file",
            lambda text, lower: lower == "generate code file" or lower.startswith("generate code file "),
            lambda text: _generate_code_file(text, ctx),
        ),
        Command(
            "generate_code",
            lambda text, lower: lower.startswith("generate code "),
            lambda text: ctx["generate_code"](strip_command_prefix(text, "generate code")),
        ),
        Command(
            "legacy_react_flask",
            lambda text, lower: "create react flask" in lower or "build react flask" in lower,
            lambda text: _generate_fullstack_project(text, ctx),
        ),
        Command(
            "legacy_flask",
            lambda text, lower: "create flask" in lower or "build flask" in lower,
            lambda text: _generate_flask_project(text, ctx),
        ),
        Command(
            "heal_preflight",
            lambda text, lower: lower.startswith("heal preflight "),
            lambda text: ctx["heal_preflight_project"](strip_command_prefix(text, "heal preflight")),
        ),
        Command(
            "heal_fullstack",
            lambda text, lower: "heal fullstack" in lower,
            lambda text: ctx["heal_fullstack_project"](_after_phrase(text, "heal fullstack")),
        ),
        Command(
            "show_logs",
            lambda text, lower: "show logs" in lower,
            lambda text: ctx["show_fullstack_logs"](_after_phrase(text, "show logs")),
        ),
        Command(
            "run_fullstack",
            lambda text, lower: "run fullstack" in lower,
            lambda text: ctx["run_fullstack_project"](_after_phrase(text, "run fullstack")),
        ),
        Command(
            "stop_all",
            lambda text, lower: lower in ["stop all apps", "stop all fullstack", "stop all projects"],
            lambda text: ctx["stop_all_fullstack_projects"](),
        ),
        Command(
            "stop_fullstack",
            lambda text, lower: "stop fullstack" in lower,
            lambda text: ctx["stop_fullstack_project"](_after_phrase(text, "stop fullstack")),
        ),
        Command(
            "reset_database",
            lambda text, lower: lower.startswith("reset database "),
            lambda text: ctx["reset_project_database"](strip_command_prefix(text, "reset database")),
        ),
        Command(
            "run_project",
            lambda text, lower: "run project" in lower,
            lambda text: ctx["self_heal_project"](_after_phrase(text, "run project"), "app.py"),
        ),
        Command(
            "snapshot",
            lambda text, lower: lower.startswith("snapshot "),
            lambda text: ctx["create_project_snapshot"](strip_command_prefix(text, "snapshot")),
        ),
        Command(
            "list_snapshots",
            lambda text, lower: lower.startswith("list snapshots "),
            lambda text: ctx["list_project_snapshots"](strip_command_prefix(text, "list snapshots")),
        ),
        Command(
            "restore_missing",
            lambda text, lower: lower.startswith("restore missing "),
            lambda text: _restore_missing(text, ctx),
        ),
        Command(
            "restore_changed",
            lambda text, lower: lower.startswith("restore changed "),
            lambda text: _restore_changed(text, ctx),
        ),
        Command(
            "restore",
            lambda text, lower: lower.startswith("restore "),
            lambda text: _restore_project(text, ctx),
        ),
        Command(
            "review_project",
            lambda text, lower: lower.startswith("review project "),
            lambda text: ctx["review_project"](strip_command_prefix(text, "review project")),
        ),
        Command(
            "compare_snapshot",
            lambda text, lower: lower.startswith("compare snapshot "),
            lambda text: _compare_snapshot(text, ctx),
        ),
        Command(
            "project_history",
            lambda text, lower: lower.startswith("project history "),
            lambda text: ctx["get_project_history"](strip_command_prefix(text, "project history")),
        ),
        Command(
            "build_from_plan",
            lambda text, lower: lower.startswith("build from plan "),
            lambda text: ctx["build_from_plan"](strip_command_prefix(text, "build from plan")),
        ),
        Command(
            "preflight_fullstack",
            lambda text, lower: lower.startswith("preflight fullstack "),
            lambda text: ctx["preflight_fullstack_project"](strip_command_prefix(text, "preflight fullstack")),
        ),
        Command(
            "validate_contract",
            lambda text, lower: lower.startswith("validate contract "),
            lambda text: ctx["validate_api_contract"](strip_command_prefix(text, "validate contract")),
        ),
        Command(
            "fix_contract",
            lambda text, lower: lower.startswith("fix contract "),
            lambda text: ctx["fix_api_contract"](strip_command_prefix(text, "fix contract")),
        ),
        Command(
            "validate_database",
            lambda text, lower: lower.startswith("validate database "),
            lambda text: ctx["validate_database_schema"](strip_command_prefix(text, "validate database")),
        ),
        Command(
            "fix_database",
            lambda text, lower: lower.startswith("fix database "),
            lambda text: ctx["fix_database_schema"](strip_command_prefix(text, "fix database")),
        ),
        Command(
            "test_endpoints",
            lambda text, lower: lower.startswith("test endpoints "),
            lambda text: ctx["test_runtime_endpoints"](strip_command_prefix(text, "test endpoints")),
        ),
        Command(
            "validate_imports",
            lambda text, lower: lower.startswith("validate imports "),
            lambda text: ctx["validate_backend_imports"](strip_command_prefix(text, "validate imports")),
        ),
        Command(
            "fix_imports",
            lambda text, lower: lower.startswith("fix imports "),
            lambda text: ctx["fix_backend_imports"](strip_command_prefix(text, "fix imports")),
        ),
        Command(
            "quality_fix",
            lambda text, lower: lower.startswith("quality fix "),
            lambda text: ctx["quality_fix_project"](strip_command_prefix(text, "quality fix")),
        ),
        Command(
            "quality_check",
            lambda text, lower: lower.startswith("quality check "),
            lambda text: ctx["quality_check_project"](strip_command_prefix(text, "quality check")),
        ),
        Command(
            "validate_app",
            lambda text, lower: lower.startswith("validate app "),
            lambda text: ctx["validate_generated_app"](strip_command_prefix(text, "validate app")),
        ),
        Command(
            "make_standalone",
            lambda text, lower: lower.startswith("make standalone "),
            lambda text: _make_standalone(text, ctx),
        ),
        Command(
            "refresh_project_ports",
            lambda text, lower: lower.startswith("refresh project ports "),
            lambda text: ctx["refresh_project_ports"](strip_command_prefix(text, "refresh project ports")),
        ),
        Command(
            "refresh_project_spec",
            lambda text, lower: lower.startswith("refresh project spec "),
            lambda text: ctx["refresh_project_spec"](strip_command_prefix(text, "refresh project spec")),
        ),
        Command(
            "clean_frontend_deps",
            lambda text, lower: lower.startswith("clean frontend deps "),
            lambda text: ctx["clean_frontend_dependencies"](strip_command_prefix(text, "clean frontend deps")),
        ),
        Command(
            "modify_app",
            lambda text, lower: lower.startswith("modify app "),
            lambda text: _modify_app(text, ctx),
        ),
        Command(
            "validate_sqlite",
            lambda text, lower: lower.startswith("validate sqlite "),
            lambda text: ctx["validate_sqlite_runtime"](strip_command_prefix(text, "validate sqlite")),
        ),
        Command(
            "fix_sqlite",
            lambda text, lower: lower.startswith("fix sqlite "),
            lambda text: ctx["fix_sqlite_runtime"](strip_command_prefix(text, "fix sqlite")),
        ),
        Command(
            "add_feature",
            lambda text, lower: lower.startswith("add feature "),
            lambda text: _add_feature(text, ctx),
        ),
        Command(
            "add_search",
            lambda text, lower: lower.startswith("add search "),
            lambda text: ctx["add_search_feature"](strip_command_prefix(text, "add search")),
        ),
    ]


def _make_standalone(user_input, ctx):
    project_name = strip_command_prefix(user_input, "make standalone")
    files = ctx["create_standalone_project_files"](project_name)
    return f"Standalone files created for {project_name}:\n{chr(10).join(files)}"


def run_agent(user_input, ctx):
    user_input = user_input.strip()

    if not user_input:
        return ctx["AGENT_HELP_TEXT"]

    user_input_lower = user_input.lower()

    if user_input_lower in ["help", "commands", "what can you do?"]:
        return ctx["AGENT_HELP_TEXT"]

    for command in build_command_registry(ctx):
        if command.matches(user_input, user_input_lower):
            return command.handle(user_input)

    if looks_like_app_build_request(user_input):
        return ctx["create_app_workflow"](f"create app {user_input}")

    return f"""Unknown command.

{ctx["AGENT_HELP_TEXT"]}
"""
