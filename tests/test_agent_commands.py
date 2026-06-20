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
