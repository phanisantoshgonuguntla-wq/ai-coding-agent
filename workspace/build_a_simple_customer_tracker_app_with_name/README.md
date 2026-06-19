# build_a_simple_customer_tracker_app_with_name

Generated standalone application.

Stack: React + Flask + SQLite

This app can run without `agent.py`, `tools.py`, or the Streamlit builder UI. Those files are only needed when you want the AI builder to create, modify, heal, or inspect generated projects.

## Backend

```text
cd backend
python -m pip install -r requirements.txt
python app.py
```

Backend URL: http://127.0.0.1:5000

## Frontend

```text
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Frontend URL: http://127.0.0.1:5173

## Windows shortcuts

- Double-click `run_backend.bat`
- Double-click `run_frontend.bat`
