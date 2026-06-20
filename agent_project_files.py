import ast
import os
import re

from agent_text import clean_code_output


WORKSPACE_DIR = "workspace"


def write_project(project_name, files_dict):
    base_path = os.path.join(WORKSPACE_DIR, project_name)
    os.makedirs(base_path, exist_ok=True)

    for file_name, content in files_dict.items():
        file_path = os.path.join(base_path, file_name)
        folder = os.path.dirname(file_path)

        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(clean_code_output(content))

    return base_path


def parse_llm_project_output(text):
    files = {}
    text = clean_code_output(text)

    pattern = r"(?:file:\s*|#\s*)([\w\.\/]+)\n(.*?)(?=(?:file:\s*|#\s*)[\w\.\/]+\n|\Z)"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

    for file_name, content in matches:
        files[file_name.strip()] = clean_code_output(content)

    return files


def detect_broken_file(error_text):
    matches = re.findall(r'File "(.+?)"', error_text)
    if not matches:
        return None
    return matches[-1]


def find_python_syntax_error(project_name):
    project_path = os.path.join(WORKSPACE_DIR, project_name)

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "venv", "node_modules"]]

        for file in files:
            if not file.endswith(".py"):
                continue

            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
                ast.parse(code)

            except SyntaxError as e:
                return file_path, str(e)

            except Exception:
                continue

    return None, None
