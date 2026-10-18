@echo off
cd /d "%~dp0"
set /p OC=Open API key (OC): 
python download_laws.py --oc %OC%
echo.
pause
