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
preview code files create snippets/math.py and snippets/text.py helper modules
save code files create snippets/math.py and snippets/text.py helper modules
preview project code <project_name> add a CSV export helper and button
save project code <project_name> add a CSV export helper and button
explain project context <project_name> add a CSV export helper and button
list codegen sessions
show codegen session <session_id>
list codegen checkpoints
show codegen checkpoint <checkpoint_id>
restore codegen checkpoint <checkpoint_id>
run fullstack <project_name>
validate app <project_name>
refresh project ports <project_name>
refresh project spec <project_name>
stop fullstack <project_name>
stop all apps
```

For generated code files, preview first and then save so the written file matches the reviewed output. If a target file already exists, the preview includes a diff before overwrite. Multi-file generation previews every target file before saving them together. In the UI, code generation includes prompt presets for common project changes such as API routes, React components, database fields, exports, and search/filter updates. Complex project-aware prompts generate an implementation plan before file previews, and the plan is included in the preview/session output.

Project-aware code generation reads the selected project's spec and prompt-relevant files, then previews changes under `workspace/<project_name>/`. Use `explain project context` to see which files will be included. Project-aware previews warn when generated Python or JavaScript imports are not declared in `backend/requirements.txt` or `frontend/package.json`, and they can include dependency patch suggestions for those files. In the UI, project-aware saves can optionally run targeted validation based on the changed files and generate a repair preview when validation fails. Use `validate app <project_name>` when you want the broader full app validation. Project-aware saves and repair saves record local codegen sessions under `workspace/_runtime/codegen_sessions/`, and the Generate Code screen includes a codegen history browser for recent sessions.

Every generated-code save creates a local checkpoint under `workspace/_runtime/codegen_checkpoints/` before writing files. Use `list codegen checkpoints`, `show codegen checkpoint <checkpoint_id>`, and `restore codegen checkpoint <checkpoint_id>` to roll back a generated save. Save results also include a read-only Git change summary with previewed files, current `git status --short`, and a suggested commit message.

## GitHub Notes

This repo should track the agent source and useful generated app source. It should not track local dependency folders, databases, build outputs, or snapshots. See `.gitignore` and `docs/GITHUB_CODEX_SETUP.md`.
