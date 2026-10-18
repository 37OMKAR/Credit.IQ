@echo off
title Credit Intelligence Workbench
cd /d "%~dp0"
set "VENV=%~dp0.venv313"
"%VENV%\Scripts\python.exe" -c "import streamlit, pymupdf, docx, openpyxl, plotly" >nul 2>nul || call setup.bat nopause
"%VENV%\Scripts\python.exe" -c "import streamlit, pymupdf, docx, openpyxl, plotly" >nul 2>nul || ( echo. & echo  Install is not complete - see messages above. & pause & exit /b 1 )
echo  Sharing on the network: other PCs open http://%COMPUTERNAME%:8501 . Starting... your browser will open http://localhost:8501  (close this window to stop the app)
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8501"
"%VENV%\Scripts\python.exe" -m streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
pause
