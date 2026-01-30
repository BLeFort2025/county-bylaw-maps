@echo off
REM ==========================================================
REM    MUNICIPAL BYLAW SCANNER - WEEKLY AUTOMATION SCRIPT
REM    "Clean Sweep" - Deletes old data, runs full pipeline
REM ==========================================================

echo.
echo ========================================
echo   BYLAW INTELLIGENCE WEEKLY SCAN
echo   %date% %time%
echo ========================================
echo.

REM --- Set Working Directory ---
cd /d "%~dp0"

REM --- STEP 1: DELETE OLD FILES (ANTI-GHOST DATA) ---
echo [1/5] Cleaning old candidate and coverage files...

REM Delete from root folder
if exist "candidates_*.csv" del /Q "candidates_*.csv"
if exist "coverage_report_*.csv" del /Q "coverage_report_*.csv"

REM Delete from signals folder
if exist "signals\candidates_*.csv" del /Q "signals\candidates_*.csv"
if exist "signals\coverage_report_*.csv" del /Q "signals\coverage_report_*.csv"

echo      Old files cleaned.
echo.

REM --- STEP 2: RUN SCANNER V1 (Robust HTTP Scanner) ---
echo [2/5] Running Scanner V1 (HTTP/PDF)...
python scanner\scanner_v1_robust.py
if errorlevel 1 (
    echo      WARNING: Scanner V1 encountered errors.
) else (
    echo      Scanner V1 complete.
)
echo.

REM --- STEP 3: RUN SCANNER V2 (Selenium Retry) ---
echo [3/5] Running Scanner V2 (Selenium Retry)...
python scanner_v2_selenium.py
if errorlevel 1 (
    echo      WARNING: Scanner V2 encountered errors.
) else (
    echo      Scanner V2 complete.
)
echo.

REM --- STEP 4: GENERATE SIGNALS ---
echo [4/5] Merging results into signals.csv...
python generate_signals.py
if errorlevel 1 (
    echo      WARNING: Signal generation encountered errors.
) else (
    echo      Signal generation complete.
)
echo.

REM --- STEP 5: LAUNCH STREAMLIT DASHBOARD ---
echo [5/5] Launching Streamlit Dashboard...
echo.
echo ========================================
echo   SCAN COMPLETE - LAUNCHING MAP
echo ========================================
echo.
streamlit run view_lower_map_v2_expiry_signals_beta.py

pause
