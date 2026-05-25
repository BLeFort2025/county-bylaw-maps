@echo off
cd /d "%~dp0"
echo Starting Daily Auto-Heal Scan for Municipal Portals...
python refresh_registry.py
echo Daily Auto-Heal Complete.
