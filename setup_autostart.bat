@echo off
chcp 65001 >nul
echo ================================================
echo   GitHub 모니터 시작 프로그램 등록
echo ================================================
echo.

set TASK_NAME=GitHub Monitor
set SCRIPT_PATH=%~dp0run.bat

:: 기존 작업 삭제 후 재등록
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "cmd /c \"%SCRIPT_PATH%\"" ^
  /sc onlogon ^
  /rl highest ^
  /f

if errorlevel 1 (
    echo [실패] 작업 스케줄러 등록에 실패했습니다.
    echo 관리자 권한으로 실행하거나, 수동으로 시작 프로그램에 추가하세요.
    echo.
    echo 수동 등록 방법:
    echo   Win+R ^> shell:startup 폴더에 run.bat 바로가기 생성
) else (
    echo [완료] 로그인 시 자동으로 모니터가 실행됩니다.
    echo.
    echo 지금 바로 시작하려면:
    echo   run.bat 을 실행하세요.
)

echo.
pause
