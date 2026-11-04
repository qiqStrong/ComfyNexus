@echo off
echo Starting Comfyui-Box (dev mode)...
cd /d "%~dp0source-code\backend"
".venv\Scripts\python.exe" -u main.py
