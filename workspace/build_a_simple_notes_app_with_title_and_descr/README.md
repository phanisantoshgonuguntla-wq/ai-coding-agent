# build_a_simple_notes_app_with_title_and_descr

Generated standalone application.

Stack: React + ASP.NET Core + SQLite

This app can run without `agent.py`, `tools.py`, or the Streamlit builder UI. Those files are only needed when you want the AI builder to create, modify, heal, or inspect generated projects.

## Backend

```text
cd backend
dotnet restore
dotnet run --urls http://127.0.0.1:5001
```

Backend URL: http://127.0.0.1:5001

## Frontend

```text
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

Frontend URL: http://127.0.0.1:5174

## Windows shortcuts

- Double-click `run_backend.bat`
- Double-click `run_frontend.bat`
