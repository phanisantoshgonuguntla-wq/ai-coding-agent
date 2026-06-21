# AI Coding Agent

A local Streamlit app that uses Ollama to build, run, inspect, validate, and modify generated full-stack applications.

## What It Can Build

- React + Flask + SQLite apps
- React + ASP.NET Core + SQLite apps
- React + PHP + SQLite apps

Generated projects live under `workspace/`. Each project can have its own ports, config, specs, validation checks, and run scripts.

## Local Setup

1. Install Python 3.11+.
2. Install Ollama and pull a small model:

   ```powershell
   ollama pull llama3.2:1b
   ```

3. Create and activate a virtual environment:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

4. Install Python dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Start the agent:

   ```powershell
   streamlit run app.py
   ```

## Testing

Run the lightweight unit tests:

```powershell
python -m pytest
```

## Useful Agent Commands

Inside the Streamlit UI, use the guided modes or run commands such as:

```text
create app build a customer tracker with name, email, phone, and notes
generate code write a Python function that validates email addresses
preview code file snippets/email_validator.py write a Python function that validates email addresses
save code file snippets/email_validator.py write a Python function that validates email addresses
generate code file snippets/email_validator.py write a Python function that validates email addresses
run fullstack <project_name>
validate app <project_name>
refresh project ports <project_name>
refresh project spec <project_name>
stop fullstack <project_name>
stop all apps
```

For generated code files, preview first and then save so the written file matches the reviewed output. If the target file already exists, the preview includes a diff before overwrite.

## GitHub Notes

This repo should track the agent source and useful generated app source. It should not track local dependency folders, databases, build outputs, or snapshots. See `.gitignore` and `docs/GITHUB_CODEX_SETUP.md`.
