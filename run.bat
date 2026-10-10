@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8501"
python -m streamlit run app.py
pause
