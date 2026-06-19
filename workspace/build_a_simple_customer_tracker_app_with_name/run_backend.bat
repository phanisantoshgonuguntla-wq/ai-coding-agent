@echo off
cd /d "%~dp0backend"
python -m pip install -r requirements.txt
python app.py
