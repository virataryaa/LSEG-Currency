@echo off
setlocal EnableDelayedExpansion
set PYTHON=C:\Users\virat.arya\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe
set LOG=C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\LSEG\Currency\Automator\run_log.txt
set INGEST_STATUS=ok
set GIT_STATUS=skipped

:: Prevent Git Credential Manager from showing an interactive dialog in unattended runs.
:: If credentials are cached it pushes silently; if not, it fails immediately instead of hanging.
set GCM_INTERACTIVE=never
set GIT_TERMINAL_PROMPT=0
echo. >> "%LOG%"
echo ============================= >> "%LOG%"
echo Run started: %date% %time% >> "%LOG%"
echo ============================= >> "%LOG%"

:: Step 1 — Coffee FX ingest (incremental, LSEG)
echo [1] Running coffee_ingest_lseg.py... >> "%LOG%"
"%PYTHON%" "C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\LSEG\Currency\Code\coffee_ingest_lseg.py" >> "%LOG%" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: coffee_ingest_lseg.py failed >> "%LOG%"
    set INGEST_STATUS=error
    goto notify
)

:: Step 2 — Cocoa FX ingest (incremental, LSEG)
echo [2] Running cocoa_ingest_lseg.py... >> "%LOG%"
"%PYTHON%" "C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\LSEG\Currency\Code\cocoa_ingest_lseg.py" >> "%LOG%" 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: cocoa_ingest_lseg.py failed >> "%LOG%"
    set INGEST_STATUS=error
    goto notify
)

:: Step 3 — Push updated parquets to GitHub
echo [3] Pushing to GitHub... >> "%LOG%"
cd /d "C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\LSEG\Currency"
git add Database\currency_data.parquet Database\cocoa_currency_data.parquet >> "%LOG%" 2>&1
git diff --cached --quiet
if %ERRORLEVEL% NEQ 0 (
    git commit -m "Auto update: Currency FX (LSEG) %date%" >> "%LOG%" 2>&1
    git pull --rebase --autostash >> "%LOG%" 2>&1
    git push >> "%LOG%" 2>&1
    if !ERRORLEVEL! NEQ 0 (
        set GIT_STATUS=failed
        echo ERROR: git push failed >> "%LOG%"
    ) else (
        set GIT_STATUS=pushed
        echo Git push done. >> "%LOG%"
    )
) else (
    echo No changes to commit. >> "%LOG%"
    set GIT_STATUS=skipped
)

:notify
echo [4] Sending email notification... >> "%LOG%"
"%PYTHON%" "C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\LSEG\Currency\Automator\notify.py" %INGEST_STATUS% %GIT_STATUS% >> "%LOG%" 2>&1

echo Run finished: %date% %time% >> "%LOG%"
