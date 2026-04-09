@echo off
echo ==========================================
echo      STARTING WEEKLY INTELLIGENCE SCAN
echo ==========================================

:: 0. REFRESH REGISTRY URLS (for JS-heavy portals like eScribe)
echo [0/6] Refreshing portal registry URLs for JS-heavy portals...
python refresh_registry.py

:: Auto-push refreshed registry to Streamlit Cloud
echo [0/6] Pushing updated registry to GitHub...
git add signals\portal_registry.csv
git commit -m "auto: weekly refresh of portal registry URLs" 2>nul
git push 2>nul

:: 1. CLEAN SWEEP
echo [1/6] Cleaning up old data files...
if exist signals\candidates_*.csv del signals\candidates_*.csv
if exist signals\coverage_report_*.csv del signals\coverage_report_*.csv
if exist candidates_*.csv del candidates_*.csv
if exist coverage_report_*.csv del coverage_report_*.csv

:: 2. RUN SCANNER V1
echo [2/6] Running Scanner V1 (HTML and PDF)...
python scanner_v1_robust.py

:: 3. RUN SCANNER V2
echo [3/6] Running Scanner V2 (Selenium for failures)...
python scanner_v2_selenium.py

:: 4. GENERATE SIGNALS
echo [4/6] Merging intelligence...
python generate_signals.py

:: 5. AUTO-PUSH SIGNAL DATA
echo [5/6] Pushing updated signals to GitHub...
git add signals\signals.csv
git commit -m "auto: weekly intelligence scan results" 2>nul
git push 2>nul

:: 6. DONE
echo ==========================================
echo      WEEKLY SCAN COMPLETE
echo ==========================================