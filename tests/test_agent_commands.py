import agent_commands
from agent_stacks import list_supported_stacks


def make_context():
    return {
        "AGENT_HELP_TEXT": "HELP TEXT",
        "list_supported_stacks": list_supported_stacks,
        "build_from_plan": lambda project: f"build:{project}",
        "modify_app": lambda project, change: f"modify:{project}:{change}",
        "add_feature": lambda project, feature: f"feature:{project}:{feature}",
        "add_search_feature": lambda project: f"search:{project}",
        "generate_code": lambda prompt: f"code:{prompt}",
        "preview_generated_code_file": lambda path, prompt: f"preview:{path}:{prompt}",
        "save_generated_code": lambda path, prompt: f"save:{path}:{prompt}",
        "preview_generated_code_files": lambda prompt: f"preview-files:{prompt}",
        "save_generated_code_files": lambda prompt: f"save-files:{prompt}",
        "preview_project_code_files": lambda project, prompt: f"preview-project:{project}:{prompt}",
        "save_generated_project_code_files": lambda project, prompt: f"save-project:{project}:{prompt}",
        "explain_project_context": lambda project, prompt: f"context:{project}:{prompt}",
        "create_app_workflow": lambda text: f"create:{text}",
    }


def test_empty_and_help_return_help_text():
    ctx = make_context()

    assert agent_commands.run_agent("", ctx) == "HELP TEXT"
    assert agent_commands.run_agent("help", ctx) == "HELP TEXT"


def test_supported_stacks_routes_to_handler():
    output = agent_commands.run_agent("supported stacks", make_context())

    assert "react_flask_sqlite" in output


def test_build_from_plan_strips_command_prefix():
    assert agent_commands.run_agent("build from plan demo_app", make_context()) == "build:demo_app"


def test_generate_code_routes_prompt_to_codegen_handler():
    assert agent_commands.run_agent("generate code write a csv parser", make_context()) == "code:write a csv parser"


def test_generate_code_file_routes_path_and_prompt_to_save_handler():
    assert agent_commands.run_agent(
        "generate code file snippets/parser.py write a csv parser",
        make_context(),
    ) == "save:snippets/parser.py:write a csv parser"


def test_preview_code_file_routes_path_and_prompt_to_preview_handler():
    assert agent_commands.run_agent(
        "preview code file snippets/parser.py write a csv parser",
        make_context(),
    ) == "preview:snippets/parser.py:write a csv parser"


def test_save_code_file_routes_path_and_prompt_to_save_handler():
    assert agent_commands.run_agent(
        "save code file snippets/parser.py write a csv parser",
        make_context(),
    ) == "save:snippets/parser.py:write a csv parser"


def test_preview_code_files_routes_prompt_to_preview_handler():
    assert agent_commands.run_agent(
        "preview code files create math.py and text.py helpers",
        make_context(),
    ) == "preview-files:create math.py and text.py helpers"


def test_save_code_files_routes_prompt_to_save_handler():
    assert agent_commands.run_agent(
        "save code files create math.py and text.py helpers",
        make_context(),
    ) == "save-files:create math.py and text.py helpers"


def test_preview_project_code_routes_project_and_prompt_to_preview_handler():
    assert agent_commands.run_agent(
        "preview project code demo_app add export button",
        make_context(),
    ) == "preview-project:demo_app:add export button"


def test_save_project_code_routes_project_and_prompt_to_save_handler():
    assert agent_commands.run_agent(
        "save project code demo_app add export button",
        make_context(),
    ) == "save-project:demo_app:add export button"


def test_explain_project_context_routes_project_and_prompt_to_handler():
    assert agent_commands.run_agent(
        "explain project context demo_app add export button",
        make_context(),
    ) == "context:demo_app:add export button"


def test_generate_code_file_validates_required_arguments():
    assert agent_commands.run_agent("generate code file", make_context()) == (
        "Use format: generate code file <workspace_path> <prompt>"
    )
    assert agent_commands.run_agent("generate code file snippets/parser.py", make_context()) == (
        "Use format: generate code file <workspace_path> <prompt>"
    )


def test_preview_and_save_code_file_validate_required_arguments():
    assert agent_commands.run_agent("preview code file", make_context()) == (
        "Use format: preview code file <workspace_path> <prompt>"
    )
    assert agent_commands.run_agent("save code file", make_context()) == (
        "Use format: save code file <workspace_path> <prompt>"
    )


def test_preview_and_save_code_files_validate_required_arguments():
    assert agent_commands.run_agent("preview code files", make_context()) == (
        "Use format: preview code files <prompt>"
    )
    assert agent_commands.run_agent("save code files", make_context()) == (
        "Use format: save code files <prompt>"
    )


def test_preview_and_save_project_code_validate_required_arguments():
    assert agent_commands.run_agent("preview project code", make_context()) == (
        "Use format: preview project code <project_name> <prompt>"
    )
    assert agent_commands.run_agent("save project code", make_context()) == (
        "Use format: save project code <project_name> <prompt>"
    )


def test_explain_project_context_validates_required_arguments():
    assert agent_commands.run_agent("explain project context", make_context()) == (
        "Use format: explain project context <project_name> <prompt>"
    )


def test_modify_app_validates_required_change_request():
    assert agent_commands.run_agent("modify app demo_app", make_context()) == (
        "Use format: modify app <project_name> <change request>"
    )
    assert agent_commands.run_agent("modify app demo_app add search", make_context()) == "modify:demo_app:add search"


def test_add_feature_validates_required_feature_request():
    assert agent_commands.run_agent("add feature demo_app", make_context()) == (
        "Use format: add feature <project_name> <feature request>"
    )
    assert agent_commands.run_agent("add feature demo_app export csv", make_context()) == "feature:demo_app:export csv"


def test_unknown_command_returns_help_text():
    output = agent_commands.run_agent("do something unusual", make_context())

    assert output.startswith("Unknown command.")
    assert "HELP TEXT" in output
