# AI Coding Agent Guidelines

## Project Overview

This repository contains a local Streamlit-based AI coding agent. The agent uses Ollama locally to plan, build, run, inspect, validate, and modify generated full-stack applications under `workspace/`.

## Commands

- Start Streamlit:
  `streamlit run app.py`
- Compile-check Python:
  `python -m py_compile agent.py tools.py app.py`
- Run the agent UI:
  open `http://127.0.0.1:8502/` or the port shown by Streamlit.

## Development Rules

- Keep `agent.py`, `tools.py`, and `app.py` as the main control surface unless a new module is clearly needed.
- Do not commit `venv`, `node_modules`, generated build outputs, SQLite DB files, or snapshots.
- Generated app source and `project_spec.json` files under `workspace/` may be committed when they are useful examples.
- Prefer stack-aware behavior for React + Flask, React + ASP.NET Core, and React + PHP projects.
- Preserve per-project ports through `project_config.json`.

## Review Guidelines

- Check that generated apps do not share stale ports, databases, or frontend API URLs.
- Check that commands fail with clear messages when Ollama, Git, npm, dotnet, or PHP are unavailable.
- Treat accidental commits of secrets, local DBs, `node_modules`, or `venv` as high-priority issues.

