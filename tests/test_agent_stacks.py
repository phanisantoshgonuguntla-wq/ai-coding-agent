from agent_stacks import (
    detect_requested_stack,
    get_stack,
    list_supported_stacks,
    looks_like_app_build_request,
)


def test_detect_requested_stack_defaults_to_flask():
    assert detect_requested_stack("build a notes app") == "react_flask_sqlite"


def test_detect_requested_stack_handles_dotnet_and_php_aliases():
    assert detect_requested_stack("build an ASP.NET inventory app") == "react_dotnet_sqlite"
    assert detect_requested_stack("create a PHP task app") == "react_php_sqlite"


def test_get_stack_falls_back_to_flask_for_unknown_key():
    assert get_stack("missing")["label"] == "React + Flask + SQLite"


def test_supported_stack_listing_includes_all_current_stacks():
    output = list_supported_stacks()

    assert "react_flask_sqlite" in output
    assert "react_dotnet_sqlite" in output
    assert "react_php_sqlite" in output


def test_looks_like_app_build_request_requires_app_and_build_intent():
    assert looks_like_app_build_request("build a customer tracker")
    assert not looks_like_app_build_request("customer tracker")
