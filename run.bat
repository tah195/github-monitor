@echo off
chcp 65001 >nul
title GitHub Monitor

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://python.org 에서 Python을 설치하세요.
    pause
    exit /b 1
)

:: requests 패키지 확인 및 설치
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo requests 패키지 설치 중...
    pip install requests
)

:: 모니터 실행
echo GitHub 모니터를 시작합니다...
python "%~dp0monitor.py"
pause
