@echo off
cd /d "%~dp0"
python -u "%~dp0run_logged_pipeline.py" --mode daily-heal
