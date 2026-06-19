@echo off
cd /d "%~dp0backend"
dotnet restore
dotnet run --urls http://127.0.0.1:5001
