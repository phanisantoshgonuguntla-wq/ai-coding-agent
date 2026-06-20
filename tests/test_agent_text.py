from agent_text import clean_code_output, make_safe_project_name, strip_command_prefix


def test_make_safe_project_name_normalizes_and_limits_length():
    name = make_safe_project_name("Build a Customer Tracker!!! With Notes and Email")

    assert name == "build_a_customer_tracker_with_notes_and_email"
    assert len(name) <= 45


def test_make_safe_project_name_falls_back_for_empty_text():
    assert make_safe_project_name("!!!") == "generated_app"


def test_strip_command_prefix_is_case_insensitive():
    assert strip_command_prefix("  Build From Plan customer_tracker", "build from plan") == "customer_tracker"


def test_clean_code_output_removes_markdown_fences():
    assert clean_code_output("```python\nprint('hello')\n```") == "print('hello')"
