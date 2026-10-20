@echo off
title Credit Intelligence Workbench - setup
cd /d "%~dp0"
set "VENV=%~dp0.venv313"
if not exist "%VENV%\Scripts\python.exe" if exist "%LOCALAPPDATA%\CreditIntelEnv\Scripts\python.exe" set "VENV=%LOCALAPPDATA%\CreditIntelEnv"
echo.
echo  === Credit Intelligence Workbench : setup ===
echo  Python environment folder: %VENV%
echo.
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do if not defined PY ( py -%%V -c "1" >nul 2>nul && set "PY=py -%%V" )
for %%V in (313 312 311 310) do if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
if not defined PY ( py -c "import sys; exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul && set "PY=py" )
if not defined PY ( python -c "import sys; exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul && set "PY=python" )
if not defined PY (
  echo  Python 3.10-3.13 was not found. Install Python 3.13 from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH", then run this again.
  pause & exit /b 1
)
echo  Using: %PY%
if not exist "%VENV%\Scripts\python.exe" (
  echo  Creating environment ...
  %PY% -m venv "%VENV%" || (
    echo  Could not create environment in %VENV%, trying %LOCALAPPDATA%\CreditIntelEnv ...
    set "VENV=%LOCALAPPDATA%\CreditIntelEnv"
    %PY% -m venv "%VENV%" || ( echo  Could not create environment & pause & exit /b 1 )
  )
)
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
set TRY=0
:pipretry
set /a TRY+=1
echo  Installing packages (attempt %TRY% of 4) ...
"%VENV%\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt && goto pipdone
if %TRY% LSS 4 ( echo  Install hiccup - retrying in 5 seconds ... & timeout /t 5 >nul & goto pipretry )
echo.
echo  Package install failed 4 times.
pause & exit /b 1
:pipdone
echo  Installing OCR engine for scanned PDFs (optional) ...
"%VENV%\Scripts\python.exe" -m pip install --no-cache-dir -r requirements-ocr.txt || echo  [warning] OCR engine did not install - scanned PDFs will need it.
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo  Setup complete.
if /i "%~1"=="nopause" goto :eof
pause
