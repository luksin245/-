@echo off
cd /d "%~dp0"
if exist __pycache__ rmdir /s /q __pycache__
python -m pip install -q -r requirements.txt
start "" cmd /c "timeout /t 5 >nul & start http://localhost:8501"
python -m streamlit run app.py
pause
