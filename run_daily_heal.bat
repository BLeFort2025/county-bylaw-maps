@echo off
cd /d "%~dp0"
echo Starting Daily Auto-Heal Scan for Municipal Portals...
python refresh_registry.py
git add signals\portal_registry.csv
git commit -m "auto: daily auto-heal of municipal portal registry URLs" 2>nul
git push origin HEAD:staging-expiry-signals 2>nul
git push origin HEAD:main 2>nul
echo Daily Auto-Heal Complete.
