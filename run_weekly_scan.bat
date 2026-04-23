@echo off
echo ==========================================
echo      STARTING WEEKLY INTELLIGENCE SCAN
echo ==========================================

:: 0. REFRESH REGISTRY URLS (for JS-heavy portals like eScribe)
echo [0/7] Refreshing portal registry URLs for JS-heavy portals...
python refresh_registry.py

:: Auto-push refreshed registry to GitHub...
echo [0/7] Pushing updated registry to GitHub...
git add signals\portal_registry.csv
git commit -m "auto: weekly refresh of portal registry URLs" 2>nul
git push 2>nul

:: 1. PRE-FETCH JS PORTAL DOCUMENTS (for Streamlit Stage 2)
echo [1/7] Pre-fetching document text from JS-rendered portals...
python selenium_prefetch.py

:: Auto-push cached docs to Streamlit Cloud
echo [1/7] Pushing cached portal docs to GitHub...
git add signals\cached_portal_docs.csv
git commit -m "auto: weekly Selenium pre-fetch of JS portal documents" 2>nul
git push 2>nul

:: 2. CLEAN SWEEP
echo [2/7] Cleaning up old data files...
if exist signals\candidates_*.csv del signals\candidates_*.csv
if exist signals\coverage_report_*.csv del signals\coverage_report_*.csv
if exist candidates_*.csv del candidates_*.csv
if exist coverage_report_*.csv del coverage_report_*.csv

:: 3. RUN SCANNER V1
echo [3/7] Running Scanner V1 (HTML and PDF)...
python scanner_v1_robust.py

:: 4. RUN SCANNER V2
echo [4/7] Running Scanner V2 (Selenium for failures)...
python scanner_v2_selenium.py

:: 5. GENERATE SIGNALS
echo [5/7] Merging intelligence...
python generate_signals.py

:: 6. AUTO-PUSH SIGNAL DATA
echo [6/7] Pushing updated signals to GitHub...
git add signals\signals.csv
git commit -m "auto: weekly intelligence scan results" 2>nul
git push 2>nul

:: 7. DONE
echo ==========================================
echo      WEEKLY SCAN COMPLETE
echo ==========================================