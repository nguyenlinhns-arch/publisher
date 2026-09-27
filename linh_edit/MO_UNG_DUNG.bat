@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%LinhEdit.exe" (
  echo Khong tim thay LinhEdit.exe trong %ROOT%
  exit /b 1
)
start "" "%ROOT%LinhEdit.exe"
exit /b 0
