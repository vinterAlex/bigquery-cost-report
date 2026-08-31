@echo off
setlocal
title BigQuery Cost Report - community edition

rem ============================================================
rem  One-click build & run helper (Windows).
rem
rem  This is just a convenience wrapper around the README
rem  commands. It does NOT need to be edited:
rem
rem    1) builds the Docker image,
rem    2) makes the  secrets  and  output  folders next to this file,
rem    3) runs the tool, mounting them into the container.
rem
rem  Put your service-account JSON key file into the  secrets
rem  folder. This script then asks you for the project id, so you can
rem  also just double-click it without typing anything first:
rem
rem       run-me.bat
rem       run-me.bat YOUR_PROJECT_ID     (skip the prompt)
rem
rem  The community edition analyses ONE dataset per run, so you must
rem  also give a dataset (as a 2nd argument, or it asks):
rem
rem       run-me.bat YOUR_PROJECT_ID YOUR_DATASET
rem
rem  The PDF + JSON report lands in the  output  folder.
rem ============================================================

rem ---- We work in the folder this file lives in --------------
cd /d "%~dp0"

rem ---- 1) project id (argument, else ask) --------------------
set "PROJECT=%~1"
if "%PROJECT%"=="" (
    set /p "PROJECT=Enter your BigQuery project id: "
)
if "%PROJECT%"=="" (
    echo.
    echo  No project id entered - nothing to run.
    echo.
    pause
    exit /b 1
)

rem ---- 1b) dataset (community = one dataset) -----------------
set "DATASET=%~2"
if "%DATASET%"=="" (
    set /p "DATASET=Enter the ONE dataset to analyse in this run: "
)
if "%DATASET%"=="" (
    echo.
    echo  This community edition needs one dataset. Pass  run-me.bat
    echo  PROJECT DATASET  or answer the prompt above.  Whole-project
    echo  scanning is a full-edition feature.
    echo.
    pause
    exit /b 1
)

rem ---- 2) folders --------------------------------------------
if not exist "secrets" mkdir "secrets"
if not exist "output" mkdir "output"

if not exist "secrets\*.json" (
    echo.
    echo  NOTE: no .json key found in the  secrets  folder.
    echo  Put your read-only Google service-account key there before
    echo  running, e.g.:  %CD%\secrets\key.json
    echo.
    pause
)

rem ---- 3) build the image only if not already built --------
docker image inspect bq-cost-report-community >nul 2>&1
if errorlevel 1 (
    echo  [1/3] Building the image...
    docker build -t bq-cost-report-community .
    if errorlevel 1 (
        echo.
        echo  ERROR: docker build failed. Is Docker Desktop running?
        pause
        exit /b 1
    )
) else (
    echo  [1/3] Image already built - skipping build.
)

rem ---- 4) run ------------------------------------------------
echo  [2/3] Running the scan on project  %PROJECT% , dataset  %DATASET% ...
docker run --rm ^
    -v "%CD%\secrets:/app/secrets" ^
    -v "%CD%\output:/app/output" ^
    bq-cost-report-community --project %PROJECT% --datasets %DATASET%
if errorlevel 1 (
    echo.
    echo  ERROR: the scan did not complete.
    echo.
    echo  Wrong project or dataset? Re-run the script with the correct
    echo  values, e.g.:  run-me.bat YOUR_PROJECT_ID YOUR_DATASET
    echo  The dataset must exist and be visible to this service account.
    echo.
    pause
    exit /b 1
)

rem ---- 5) done -----------------------------------------------
echo  [3/3] Done. Your report is in:  %CD%\output\%PROJECT%\
pause
