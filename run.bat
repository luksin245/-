@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo  사업용 통장 거래내역 관리 프로그램 실행
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.
    echo        https://www.python.org/downloads/ 에서 Python 3.11 이상을 설치한 뒤,
    echo        설치 화면에서 "Add python.exe to PATH" 옵션을 반드시 체크해주세요.
    echo.
    pause
    exit /b 1
)

python -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo [오류] 필요한 패키지가 설치되어 있지 않습니다.
    echo        먼저 아래 명령을 실행해 패키지를 설치해주세요.
    echo.
    echo        pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Python 및 필요한 패키지 확인을 완료했습니다. 프로그램을 실행합니다...
echo 잠시 후 브라우저가 자동으로 열립니다. (열리지 않으면 http://localhost:8501 로 직접 접속하세요)
echo.
echo 프로그램을 종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.
echo.

streamlit run app.py

pause
