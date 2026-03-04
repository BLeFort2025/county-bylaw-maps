@echo off
echo ==========================================
echo      STARTING WEEKLY INTELLIGENCE SCAN
echo ==========================================

:: 1. CLEAN SWEEP
echo [1/5] Cleaning up old data files...
if exist signals\candidates_*.csv del signals\candidates_*.csv
if exist signals\coverage_report_*.csv del signals\coverage_report_*.csv
if exist candidates_*.csv del candidates_*.csv
if exist coverage_report_*.csv del coverage_report_*.csv

:: 2. RUN SCANNER V1
echo [2/5] Running Scanner V1 (HTML and PDF)...
python scanner_v1_robust.py

:: 3. RUN SCANNER V2
echo [3/5] Running Scanner V2 (Selenium for failures)...
python scanner_v2_selenium.py

:: 4. GENERATE SIGNALS
echo [4/5] Merging intelligence...
python generate_signals.py

:: 5. LAUNCH MAP
echo [5/5] Launching Map...
streamlit run app.py